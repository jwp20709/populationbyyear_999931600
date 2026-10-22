
import json
import re
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

# ---------------------------------------
# 기본 설정
# ---------------------------------------
st.set_page_config(
    page_title="전국 고령화 단계구분도",
    page_icon="🗺️",
    layout="wide"
)

DATA_URL = (
    "https://raw.githubusercontent.com/"
    "first2022-cyber/contents/main/"
    "population_ts_yearly_gender.zip"
)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/"
    "first2022-cyber/contents/main/"
    "sigungu_kr.geojson"
)

st.markdown("""
<style>
.stApp {
    background-color: #fffaf0;
}
h1, h2, h3 {
    color: #704214;
}
div[data-testid="stMetric"] {
    background: #fff0c2;
    padding: 18px;
    border-radius: 14px;
    border: 1px solid #f0d78c;
}
</style>
""", unsafe_allow_html=True)

st.title("🗺️ 전국 고령화 단계구분도")
st.caption(
    "2026년 6월 기준 · 전국 시군구별 65세 이상 인구 비율"
)

# ---------------------------------------
# 데이터 불러오기
# ---------------------------------------
@st.cache_data(ttl=3600)
def load_population():
    response = requests.get(DATA_URL, timeout=120)
    response.raise_for_status()

    # pandas가 ZIP 압축 CSV를 직접 읽음
    from io import BytesIO
    df = pd.read_csv(BytesIO(response.content), compression="zip",
                     dtype={"코드": "string"})

    required = ["연도", "코드"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"인구 데이터에 필요한 열이 없습니다: {missing}")

    # 연도 자료형 통일 후 2026년만 선택
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
    df = df[df["연도"] == 2026].copy()

    if df.empty:
        raise ValueError("인구 데이터에서 2026년 자료를 찾지 못했습니다.")

    # 동 코드의 앞 5자리를 시군구 코드로 사용
    df["코드"] = (
        df["코드"].astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(10)
        .str[:5]
    )

    # 계_로 시작하는 연령별 인구 열만 선택
    total_cols = [
        c for c in df.columns
        if c.startswith("계_")
    ]

    # 계_65세부터 계_100세 이상까지
    elderly_cols = [
        c for c in total_cols
        if re.match(r"^계_(?:[6-9]\d|100)세(?:$| )", c)
        or c == "계_100세 이상"
    ]

    # 실제 열 이름이 '계_65세', '계_66세', ... 형식인지 검사
    if not total_cols:
        raise ValueError("'계_'로 시작하는 인구 열을 찾지 못했습니다.")

    if not elderly_cols:
        raise ValueError(
            "65세 이상 열을 찾지 못했습니다. "
            "열 이름이 '계_65세', '계_100세 이상' 형식인지 확인하세요."
        )

    # 문자열 숫자도 안전하게 숫자로 변환
    for c in set(total_cols):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # 시군구 코드별 합산
    grouped = df.groupby("코드", as_index=False)[total_cols].sum()

    grouped["전체인구"] = grouped[total_cols].sum(axis=1)
    grouped["65세이상인구"] = grouped[elderly_cols].sum(axis=1)

    grouped["고령화율"] = (
        grouped["65세이상인구"]
        .div(grouped["전체인구"].where(grouped["전체인구"] > 0))
        .mul(100)
    )

    return grouped[["코드", "전체인구", "65세이상인구", "고령화율"]]


@st.cache_data(ttl=3600)
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=60)
    response.raise_for_status()
    geo = response.json()

    # GeoJSON의 코드도 문자열로 통일
    for feature in geo.get("features", []):
        props = feature.setdefault("properties", {})
        code = props.get("코드")

        if code is not None:
            code = str(code).strip()
            if code.endswith(".0"):
                code = code[:-2]
            props["코드"] = code.zfill(5)

    return geo


# ---------------------------------------
# 지도 그리기
# ---------------------------------------
try:
    with st.spinner("인구 자료와 시군구 경계를 불러오는 중입니다..."):
        population = load_population()
        geojson = load_geojson()

    # 경계 코드 목록 확인
    geo_codes = {
        f["properties"].get("코드")
        for f in geojson.get("features", [])
        if f.get("properties", {}).get("코드") is not None
    }

    # 코드 기준으로 결합: 지역명으로 결합하지 않음
    map_df = population.merge(
        pd.DataFrame({"코드": sorted(geo_codes)}),
        on="코드",
        how="inner",
        validate="one_to_one"
    )

    if map_df.empty:
        st.error(
            "인구 데이터와 GeoJSON의 코드가 일치하지 않습니다. "
            "두 파일의 코드 형식과 연도를 확인해 주세요."
        )
        st.stop()

    # GeoJSON의 시군구 이름을 코드로 연결
    name_by_code = {
        f["properties"]["코드"]: f["properties"].get("시군구", "")
        for f in geojson.get("features", [])
        if f.get("properties", {}).get("코드") is not None
    }
    map_df["시군구명"] = map_df["코드"].map(name_by_code)

    # 지표 카드
    total_population = int(map_df["전체인구"].sum())
    elderly_population = int(map_df["65세이상인구"].sum())
    total_rate = (
        elderly_population / total_population * 100
        if total_population > 0 else 0
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("📍 지도에 포함된 시군구", f"{len(map_df):,}개")
    c2.metric("👵 65세 이상 인구", f"{elderly_population:,}명")
    c3.metric("📊 전국 고령화율", f"{total_rate:.2f}%")

    st.markdown("### 시군구별 고령화율")
    st.write(
        "색이 진할수록 65세 이상 인구 비율이 높습니다. "
        "지역 위에 마우스를 올리면 이름과 고령화율을 확인할 수 있습니다."
    )

    fig = px.choropleth(
        map_df,
        geojson=geojson,
        locations="코드",
        featureidkey="properties.코드",
        color="고령화율",
        color_continuous_scale=[
            "#fff7bc",
            "#fec44f",
            "#fe9929",
            "#ec7014",
            "#993404"
        ],
        hover_name="시군구명",
        hover_data={
            "코드": False,
            "시군구명": False,
            "고령화율": ":.2f",
            "전체인구": ":,",
            "65세이상인구": ":,"
        },
        labels={
            "고령화율": "고령화율(%)",
            "전체인구": "전체 인구",
            "65세이상인구": "65세 이상 인구"
        }
    )

    # 타일 없는 지도: GeoJSON 경계만 사용
    fig.update_geos(
        visible=False,
        fitbounds="locations",
        showcountries=False,
        showcoastlines=False,
        showland=False,
        showframe=False,
        bgcolor="#fffaf0"
    )

    fig.update_traces(
        marker_line_color="#777777",
        marker_line_width=0.45,
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "고령화율: %{z:.2f}%<br>"
            "<extra></extra>"
        )
    )

    fig.update_layout(
        height=780,
        margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor="#fffaf0",
        plot_bgcolor="#fffaf0",
        coloraxis_colorbar=dict(
            title="고령화율(%)",
            ticksuffix="%"
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        f"인구 자료 코드와 경계 코드가 일치하는 "
        f"{len(map_df):,}개 시군구를 표시했습니다."
    )

    # 데이터 점검용 표
    with st.expander("📋 시군구별 고령화율 표 보기"):
        table = map_df[
            ["코드", "시군구명", "전체인구", "65세이상인구", "고령화율"]
        ].copy()
        table = table.sort_values("고령화율", ascending=False)
        table["고령화율"] = table["고령화율"].round(2)
        st.dataframe(table, use_container_width=True, hide_index=True)

except Exception as e:
    st.error("데이터를 불러오거나 지도를 만드는 중 오류가 발생했습니다.")
    st.exception(e)
