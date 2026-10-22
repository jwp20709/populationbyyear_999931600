
import re
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
import plotly.express as px


# =========================================================
# 1. 페이지 설정 및 디자인
# =========================================================
st.set_page_config(
    page_title="전국 고령화 단계구분도",
    page_icon="🗺️",
    layout="wide",
)

DATA_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/population_ts_yearly_gender.zip"
)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)

st.markdown(
    """
    <style>
    .stApp {
        background-color: #fffaf0;
    }
    h1, h2, h3 {
        color: #704214;
    }
    div[data-testid="stMetric"] {
        background-color: #fff0c2;
        border: 1px solid #efd58b;
        border-radius: 14px;
        padding: 16px;
    }
    div[data-testid="stMetricLabel"] {
        color: #704214;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🗺️ 전국 고령화 단계구분도")
st.caption(
    "연도와 지표를 선택해 우리나라 시군구별 인구 구조를 비교해 보세요."
)


# =========================================================
# 2. 행정구역 코드 정리
# =========================================================
def normalize_code(value):
    """행정구역 코드를 5자리 문자열로 통일한다."""
    if pd.isna(value):
        return None

    digits = re.sub(r"\D", "", str(value).strip())

    if not digits:
        return None

    # 읍·면·동 코드처럼 5자리보다 긴 코드는 앞 5자리 사용
    code = digits[:5] if len(digits) >= 5 else digits.zfill(5)

    # 구 행정구역 코드 -> 현재 경계 코드
    if code == "47720":
        code = "27720"
    elif code.startswith("42"):
        code = "51" + code[2:]
    elif code.startswith("45"):
        code = "52" + code[2:]

    return code


def normalize_geo_code(value):
    """GeoJSON의 코드는 5자리 문자열로 통일하되 재매핑하지 않는다."""
    if pd.isna(value):
        return None

    digits = re.sub(r"\D", "", str(value).strip())

    if not digits:
        return None

    return digits[:5] if len(digits) >= 5 else digits.zfill(5)


# =========================================================
# 3. 인구 데이터 불러오기 및 연령별 지표 계산
# =========================================================
@st.cache_data(ttl=3600)
def load_population():
    response = requests.get(DATA_URL, timeout=180)
    response.raise_for_status()

    df = pd.read_csv(
        BytesIO(response.content),
        compression="zip",
        dtype={"코드": "string"},
        low_memory=False,
    )

    required = ["연도", "코드"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            f"인구 자료에 필요한 열이 없습니다: {missing}"
        )

    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
    df = df.dropna(subset=["연도", "코드"]).copy()
    df["연도"] = df["연도"].astype(int)

    # 계_로 시작하는 연령별 인구 열만 사용한다.
    # 남_ / 여_ 열은 중복 합산하지 않는다.
    total_cols = [
        c for c in df.columns
        if c.startswith("계_")
        and re.match(r"^계_\d+세", c)
    ]

    if not total_cols:
        raise ValueError(
            "인구 열을 찾지 못했습니다. "
            "'계_0세', '계_65세' 등의 열이 있는지 확인하세요."
        )

    # 열 이름에서 나이를 추출한다.
    age_by_col = {}
    for col in total_cols:
        match = re.match(r"^계_(\d+)세", col)
        if match:
            age_by_col[col] = int(match.group(1))

    elderly_cols = [
        c for c, age in age_by_col.items() if age >= 65
    ]
    youth_cols = [
        c for c, age in age_by_col.items() if 0 <= age <= 14
    ]

    if not elderly_cols:
        raise ValueError("65세 이상 인구 열을 찾지 못했습니다.")

    if not youth_cols:
        raise ValueError("0~14세 인구 열을 찾지 못했습니다.")

    # 인구 수치 변환
    for col in total_cols:
        df[col] = pd.to_numeric(
            df[col], errors="coerce"
        ).fillna(0)

    # 읍·면·동 코드 -> 시군구 코드
    df["코드"] = df["코드"].map(normalize_code)
    df = df.dropna(subset=["코드"]).copy()

    # 연도별·시군구별 인구 합산
    grouped = (
        df.groupby(["연도", "코드"], as_index=False)[total_cols]
        .sum()
    )

    grouped["전체인구"] = grouped[total_cols].sum(axis=1)
    grouped["65세이상인구"] = grouped[elderly_cols].sum(axis=1)
    grouped["유소년인구"] = grouped[youth_cols].sum(axis=1)

    denominator = grouped["전체인구"].where(
        grouped["전체인구"] > 0
    )

    grouped["고령화율(%)"] = (
        grouped["65세이상인구"] / denominator * 100
    )
    grouped["유소년비율(%)"] = (
        grouped["유소년인구"] / denominator * 100
    )

    result = grouped[
        [
            "연도",
            "코드",
            "전체인구",
            "65세이상인구",
            "유소년인구",
            "고령화율(%)",
            "유소년비율(%)",
        ]
    ].copy()

    # 전국 지표는 경계 파일과 일치하는 지역만이 아니라
    # 인구 데이터 전체를 대상으로 계산한다.
    national = (
        result.groupby("연도", as_index=False)[
            ["전체인구", "65세이상인구", "유소년인구"]
        ]
        .sum()
    )

    national["고령화율(%)"] = (
        national["65세이상인구"]
        / national["전체인구"].where(national["전체인구"] > 0)
        * 100
    )
    national["유소년비율(%)"] = (
        national["유소년인구"]
        / national["전체인구"].where(national["전체인구"] > 0)
        * 100
    )

    return result, national


# =========================================================
# 4. GeoJSON 불러오기
# =========================================================
@st.cache_data(ttl=3600)
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=90)
    response.raise_for_status()
    geo = response.json()

    if geo.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON이 FeatureCollection 형식이 아닙니다.")

    for feature in geo.get("features", []):
        props = feature.setdefault("properties", {})

        if props.get("코드") is not None:
            props["코드"] = normalize_geo_code(props["코드"])

    return geo


# =========================================================
# 5. 단계별 색상 구간
# =========================================================
AGEING_BINS = [-float("inf"), 19, 23, 28, 38, float("inf")]
AGEING_LABELS = [
    "19% 미만",
    "19~23%",
    "23~28%",
    "28~38%",
    "38% 이상",
]
AGEING_COLORS = {
    "19% 미만": "#fff7bc",
    "19~23%": "#fec44f",
    "23~28%": "#fe9929",
    "28~38%": "#ec7014",
    "38% 이상": "#993404",
}

# 유소년 비율은 고령화율과 별도의 구간으로 비교한다.
# 연도별 비교가 가능하도록 유소년 구간도 고정한다.
YOUTH_BINS = [-float("inf"), 6, 9, 12, 15, float("inf")]
YOUTH_LABELS = [
    "6% 미만",
    "6~9%",
    "9~12%",
    "12~15%",
    "15% 이상",
]
YOUTH_COLORS = {
    "6% 미만": "#f7fbff",
    "6~9%": "#c6dbef",
    "9~12%": "#6baed6",
    "12~15%": "#3182bd",
    "15% 이상": "#084594",
}

NO_DATA = "자료 없음"
NO_DATA_COLOR = "#c8c8c8"


def add_color_group(df, metric):
    """지표값을 고정된 단계 구간에 배정한다."""
    df = df.copy()

    if metric == "고령화율":
        bins = AGEING_BINS
        labels = AGEING_LABELS
    else:
        bins = YOUTH_BINS
        labels = YOUTH_LABELS

    df["구간"] = pd.cut(
        df["비율(%)"],
        bins=bins,
        labels=labels,
        right=False,
        include_lowest=True,
    ).astype("object")

    df["구간"] = df["구간"].where(
        df["비율(%)"].notna(), NO_DATA
    )

    color_map = (
        AGEING_COLORS if metric == "고령화율"
        else YOUTH_COLORS
    )
    color_map = {**color_map, NO_DATA: NO_DATA_COLOR}
    category_order = labels + [NO_DATA]

    return df, color_map, category_order


# =========================================================
# 6. 앱 실행
# =========================================================
try:
    with st.spinner("인구 데이터와 행정구역 경계를 불러오는 중입니다..."):
        population, national = load_population()
        geojson = load_geojson()

    years = sorted(population["연도"].unique().tolist())

    if not years:
        st.error("사용할 수 있는 연도 데이터가 없습니다.")
        st.stop()

    # -------------------------------------
    # 선택 컨트롤
    # -------------------------------------
    st.subheader("🔎 지도 설정")

    col_year, col_province, col_metric = st.columns([1, 1.3, 1.3])

    with col_year:
        selected_year = st.slider(
            "연도 선택",
            min_value=int(min(years)),
            max_value=int(max(years)),
            value=int(max(years)),
            step=1,
            help="연도를 옮기면 해당 연도의 인구 자료로 지도가 바뀝니다.",
        )

    # GeoJSON에 실제로 들어 있는 시도 목록 사용
    province_names = sorted({
        str(f.get("properties", {}).get("시도", "")).strip()
        for f in geojson.get("features", [])
        if f.get("properties", {}).get("시도")
    })

    with col_province:
        selected_province = st.selectbox(
            "시도 선택",
            options=["전국"] + province_names,
            index=0,
        )

    with col_metric:
        selected_metric = st.selectbox(
            "표시할 지표",
            options=["고령화율", "유소년 비율"],
            index=0,
            help=(
                "고령화율은 65세 이상 인구 비율, "
                "유소년 비율은 0~14세 인구 비율입니다."
            ),
        )

    # -------------------------------------
    # 선택 연도 데이터
    # -------------------------------------
    year_df = population[
        population["연도"] == selected_year
    ].copy()

    national_row = national[national["연도"] == selected_year]

    if year_df.empty or national_row.empty:
        st.warning(
            f"{selected_year}년 데이터가 없습니다. "
            "다른 연도를 선택해 주세요."
        )
        st.stop()

    national_row = national_row.iloc[0]

    # -------------------------------------
    # 지도에 사용할 GeoJSON 필터링
    # -------------------------------------
    all_features = geojson.get("features", [])

    if selected_province == "전국":
        selected_features = all_features
    else:
        selected_features = [
            f for f in all_features
            if str(f.get("properties", {}).get("시도", "")).strip()
            == selected_province
        ]

    if not selected_features:
        st.warning("선택한 시도의 경계 자료가 없습니다.")
        st.stop()

    # 시군구 코드별로 지도에 필요한 속성 구성
    geo_rows = []
    for feature in selected_features:
        props = feature.get("properties", {})
        code = props.get("코드")

        if code is None:
            continue

        geo_rows.append({
            "코드": str(code),
            "시도": props.get("시도", ""),
            "시군구": props.get("시군구", ""),
        })

    geo_table = pd.DataFrame(geo_rows)

    if geo_table.empty:
        st.error("지도에 사용할 시군구 코드가 없습니다.")
        st.stop()

    # 코드가 중복된 경계가 있다면 첫 번째만 사용
    geo_table = geo_table.drop_duplicates(
        subset=["코드"], keep="first"
    )

    # 코드로만 결합. 이름으로 결합하지 않는다.
    map_df = geo_table.merge(
        year_df,
        on="코드",
        how="left",
        validate="one_to_one",
    )

    # 선택 지표에 맞는 비율 열 선택
    if selected_metric == "고령화율":
        rate_col = "고령화율(%)"
        rate_title = "고령화율"
    else:
        rate_col = "유소년비율(%)"
        rate_title = "유소년 비율"

    map_df["비율(%)"] = map_df[rate_col]

    map_df, color_map, category_order = add_color_group(
        map_df, selected_metric
    )

    # -------------------------------------
    # 지도 위 지표 카드 3개
    # -------------------------------------
    st.markdown("### 📊 주요 지표")

    metric_cols = st.columns(3)

    national_rate = national_row[rate_col]

    valid_map = map_df.dropna(subset=["비율(%)"]).copy()

    if not valid_map.empty:
        highest = valid_map.loc[valid_map["비율(%)"].idxmax()]
        lowest = valid_map.loc[valid_map["비율(%)"].idxmin()]

        high_text = (
            f"{highest['시군구']} · {highest['비율(%)']:.2f}%"
        )
        low_text = (
            f"{lowest['시군구']} · {lowest['비율(%)']:.2f}%"
        )
    else:
        high_text = "자료 없음"
        low_text = "자료 없음"

    metric_cols[0].metric(
        f"🇰🇷 전국 {rate_title}",
        f"{national_rate:.2f}%",
        help=(
            "해당 연도의 전국 인구 자료를 합산해 계산합니다. "
            "지도에 표시되는 지역 수와는 별개입니다."
        ),
    )
    metric_cols[1].metric(
        f"🔴 가장 높은 시군구",
        high_text,
        help="선택한 시도 범위에서 가장 높은 지역입니다.",
    )
    metric_cols[2].metric(
        f"🔵 가장 낮은 시군구",
        low_text,
        help="선택한 시도 범위에서 가장 낮은 지역입니다.",
    )

    # -------------------------------------
    # 단계구분도
    # -------------------------------------
    st.markdown(
        f"### 🗺️ {selected_year}년 {selected_province} {rate_title} 단계구분도"
    )

    if selected_metric == "고령화율":
        st.caption(
            "고정 구간: 19% · 23% · 28% · 38% "
            "(연도를 바꿔도 색상 기준은 동일합니다.)"
        )
    else:
        st.caption(
            "유소년 비율 구간: 6% · 9% · 12% · 15% "
            "(고령화율과 다른 고정 구간을 사용합니다.)"
        )

    # 선택 시도만 남긴 GeoJSON으로 확대
    filtered_geojson = {
        "type": "FeatureCollection",
        "features": selected_features,
    }

    fig = px.choropleth(
        map_df,
        geojson=filtered_geojson,
        locations="코드",
        featureidkey="properties.코드",
        color="구간",
        category_orders={"구간": category_order},
        color_discrete_map=color_map,
        hover_name="시군구",
        hover_data={
            "코드": False,
            "시도": False,
            "구간": False,
            "비율(%)": ":.2f",
        },
        labels={
            "비율(%)": f"{rate_title}(%)",
            "구간": "색상 구간",
        },
    )

    fig.update_traces(
        marker_line_color="#777777",
        marker_line_width=0.45,
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            f"{rate_title}: " + "%{customdata[3]:.2f}%"
            "<extra></extra>"
        ),
    )

    # 타일 없이 GeoJSON 경계만 표시
    fig.update_geos(
        visible=False,
        fitbounds="locations",
        showcountries=False,
        showcoastlines=False,
        showland=False,
        showframe=False,
        bgcolor="#fffaf0",
    )

    fig.update_layout(
        height=760,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="#fffaf0",
        plot_bgcolor="#fffaf0",
        legend_title_text=f"{rate_title} 구간",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.03,
            xanchor="center",
            x=0.5,
        ),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displaylogo": False},
    )

    # -------------------------------------
    # 경계와 맞지 않는 지역 안내
    # -------------------------------------
    unmatched = map_df[map_df["비율(%)"].isna()].copy()

    if not unmatched.empty:
        st.warning(
            f"회색 지역 {len(unmatched)}곳은 선택한 연도의 인구 자료와 "
            "현재 경계 코드가 일치하지 않거나 유효한 비율을 계산할 수 "
            "없어 색상을 표시하지 않았습니다. "
            "행정구역 코드 변경 및 자료 누락 여부를 확인해 주세요."
        )

        unmatched_names = unmatched["시군구"].dropna().astype(str).tolist()

        if unmatched_names:
            shown_names = unmatched_names[:20]
            suffix = (
                f" 외 {len(unmatched_names) - 20}곳"
                if len(unmatched_names) > 20 else ""
            )
            st.caption(
                "확인 대상: " + ", ".join(shown_names) + suffix
            )
    else:
        st.success(
            "선택한 지도 범위의 모든 경계에서 유효한 비율을 계산했습니다."
        )

    # -------------------------------------
    # 표 보기
    # -------------------------------------
    with st.expander("📋 시군구별 상세 자료 보기"):
        display_cols = [
            "코드",
            "시도",
            "시군구",
            "전체인구",
            "65세이상인구",
            "유소년인구",
            "고령화율(%)",
            "유소년비율(%)",
        ]

        table = map_df[display_cols].copy()
        table = table.sort_values(
            rate_col, ascending=False, na_position="last"
        )

        table["고령화율(%)"] = table["고령화율(%)"].round(2)
        table["유소년비율(%)"] = table["유소년비율(%)"].round(2)

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

except requests.RequestException as e:
    st.error(
        "데이터 다운로드에 실패했습니다. "
        "Streamlit Cloud의 인터넷 연결과 데이터 URL을 확인해 주세요."
    )
    st.exception(e)

except Exception as e:
    st.error("앱을 실행하는 중 오류가 발생했습니다.")
    st.exception(e)
