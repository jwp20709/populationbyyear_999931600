
# main.py
# 동네별 인구 피라미드
# 초보자도 이해하기 쉽도록 주요 코드에 한국어 주석을 달았습니다.

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go


# --------------------------------------------------
# 1. 페이지 기본 설정
# --------------------------------------------------
st.set_page_config(
    page_title="동네별 인구 피라미드",
    page_icon="🏘️",
    layout="wide",
)

DATA_URL = (
    "https://raw.githubusercontent.com/"
    "jwp20709-cyber/contents/main/"
    "population_ts_yearly_gender.zip"
)

# 따뜻한 느낌의 색상
BACKGROUND = "#FFF9F2"
MALE_COLOR = "#6C91C2"
FEMALE_COLOR = "#D98282"
TEXT_COLOR = "#493D35"


# --------------------------------------------------
# 2. 화면 디자인 (CSS)
# --------------------------------------------------
st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {BACKGROUND};
        color: {TEXT_COLOR};
    }}

    h1, h2, h3 {{
        color: {TEXT_COLOR};
    }}

    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid #F0E3D5;
        border-radius: 14px;
        padding: 16px;
    }}

    div[data-testid="stSelectbox"] label {{
        color: {TEXT_COLOR};
        font-weight: 600;
    }}

    .intro {{
        background: #FFF0DF;
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 18px;
        line-height: 1.8;
    }}

    .insight {{
        background: #FFF0DF;
        border-left: 5px solid #D9A66C;
        border-radius: 10px;
        padding: 14px 18px;
        margin-top: 12px;
        margin-bottom: 18px;
        line-height: 1.7;
        color: {TEXT_COLOR};
    }}

    .footer {{
        color: #8C7B6D;
        font-size: 13px;
        text-align: center;
        margin-top: 28px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# 3. 데이터 불러오기
# --------------------------------------------------
@st.cache_data(show_spinner="전국 읍·면·동 인구 데이터를 불러오는 중...")
def load_data():
    """
    ZIP 압축 파일을 pandas로 읽고, 가장 최신 연도만 남깁니다.
    """

    # URL이 ZIP 파일이어도 pandas가 직접 읽을 수 있습니다.
    df = pd.read_csv(DATA_URL, compression="zip")

    # 열 이름 앞뒤에 공백이 있다면 제거합니다.
    df.columns = df.columns.astype(str).str.strip()

    if "연도" not in df.columns:
        raise ValueError("'연도' 열을 찾을 수 없습니다.")

    # 연도 열이 문자열이어도 숫자로 변환합니다.
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
    df = df.dropna(subset=["연도"]).copy()
    df["연도"] = df["연도"].astype(int)

    # 가장 최신 연도만 남깁니다.
    latest_year = int(df["연도"].max())
    df = df[df["연도"] == latest_year].copy()

    # 지역 이름의 공백을 정리합니다.
    for col in ["시도", "시군구", "동"]:
        if col not in df.columns:
            raise ValueError(f"'{col}' 열을 찾을 수 없습니다.")
        df[col] = df[col].fillna("").astype(str).str.strip()

    # 0~99세와 100세 이상까지 101개 연령 구간을 만듭니다.
    ages = [f"{i}세" for i in range(101)]
    ages[-1] = "100세 이상"

    population_columns = []
    for age in ages:
        population_columns.extend([f"남_{age}", f"여_{age}"])

    # 인구 열이 누락된 경우 원인을 명확하게 알려줍니다.
    missing = [c for c in population_columns if c not in df.columns]
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(
            "필요한 인구 열이 없습니다: "
            f"{preview}"
            + (" ..." if len(missing) > 10 else "")
        )

    # 인구 값이 문자로 저장된 경우도 숫자로 변환합니다.
    for col in population_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df, latest_year, ages


# --------------------------------------------------
# 4. 제목 및 안내 문구
# --------------------------------------------------
st.title("🏘️ 동네별 인구 피라미드")

st.markdown(
    """
    <div class="intro">
        전국 읍·면·동의 최신 인구 구성을 살펴보세요.<br>
        <b>시도 → 시군구 → 동</b> 순서로 지역을 선택하면
        남녀별 연령 분포와 인구 지표를 확인할 수 있습니다.
    </div>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# 5. 데이터 오류 안내
# --------------------------------------------------
try:
    df, latest_year, ages = load_data()
except Exception as e:
    st.error("인구 데이터를 불러오지 못했습니다.")
    st.exception(e)
    st.info("인터넷 연결, 데이터 URL, CSV 열 이름을 확인해 주세요.")
    st.stop()


# --------------------------------------------------
# 6. 지역 선택 드롭다운 3개
# --------------------------------------------------
st.subheader("📍 지역 선택")

col1, col2, col3 = st.columns(3)

# 첫 번째 드롭다운: 시도
sido_list = sorted(df["시도"].dropna().unique().tolist())

with col1:
    selected_sido = st.selectbox(
        "① 시도",
        options=sido_list,
        key="selected_sido",
    )

# 선택한 시도에 속한 시군구만 보여줍니다.
sido_df = df[df["시도"] == selected_sido]
sigungu_list = sorted(sido_df["시군구"].dropna().unique().tolist())

with col2:
    selected_sigungu = st.selectbox(
        "② 시군구",
        options=sigungu_list,
        key="selected_sigungu",
    )

# 선택한 시도와 시군구에 속한 동만 보여줍니다.
sigungu_df = sido_df[sido_df["시군구"] == selected_sigungu]
dong_list = sorted(sigungu_df["동"].dropna().unique().tolist())

with col3:
    selected_dong = st.selectbox(
        "③ 동",
        options=dong_list,
        key="selected_dong",
    )


# --------------------------------------------------
# 7. 선택한 동네의 인구 자료 추출
# --------------------------------------------------
area_df = sigungu_df[sigungu_df["동"] == selected_dong]

if area_df.empty:
    st.warning("선택한 지역의 인구 자료가 없습니다.")
    st.stop()

# 한 지역이 여러 행으로 존재할 수 있으므로 나이별로 합산합니다.
male_values = []
female_values = []

for age in ages:
    male_col = f"남_{age}"
    female_col = f"여_{age}"

    male_count = pd.to_numeric(
        area_df[male_col], errors="coerce"
    ).fillna(0).sum()

    female_count = pd.to_numeric(
        area_df[female_col], errors="coerce"
    ).fillna(0).sum()

    male_values.append(int(male_count))
    female_values.append(int(female_count))

# 남성은 왼쪽으로 표시하기 위해 음수로 바꿉니다.
male_negative = [-v for v in male_values]

# 남녀를 합쳐 연령별 전체 인구를 계산합니다.
age_totals = [
    male + female for male, female in zip(male_values, female_values)
]
total_male = sum(male_values)
total_female = sum(female_values)
total_population = total_male + total_female

# 평균연령은 각 연령의 인구를 가중치로 계산합니다.
# '100세 이상'은 대표 연령을 100세로 간주합니다.
if total_population > 0:
    weighted_age_sum = sum(
        age_index * count
        for age_index, count in enumerate(age_totals)
    )
    average_age = weighted_age_sum / total_population
else:
    average_age = 0.0

# 고령화율: 전체 인구 중 65세 이상 인구의 비율
# 65세부터 100세 이상까지의 구간을 합산합니다.
elderly_population = sum(age_totals[65:])
aging_rate = (
    elderly_population / total_population * 100
    if total_population > 0
    else 0.0
)

# 아이 인구 비율: 0~14세 인구의 비율
child_population = sum(age_totals[:15])
child_rate = (
    child_population / total_population * 100
    if total_population > 0
    else 0.0
)


# --------------------------------------------------
# 8. 선택 지역 및 지표 카드 3개
# --------------------------------------------------
st.markdown("---")
st.subheader(f"📊 {selected_sido} {selected_sigungu} {selected_dong}")

card1, card2, card3 = st.columns(3)

with card1:
    st.metric(
        label="👥 총인구",
        value=f"{total_population:,}명",
    )

with card2:
    st.metric(
        label="🎂 평균연령",
        value=f"{average_age:.1f}세",
        help="연령별 인구를 가중치로 계산한 평균입니다. 100세 이상은 100세로 계산합니다.",
    )

with card3:
    # 고령화율이 20%를 넘으면 카드 라벨에 주의 표시를 붙입니다.
    aging_label = (
        "⚠️ 고령화율 (65세 이상)"
        if aging_rate > 20
        else "🌳 고령화율 (65세 이상)"
    )
    st.metric(
        label=aging_label,
        value=f"{aging_rate:.1f}%",
        help="전체 인구 중 65세 이상 인구가 차지하는 비율입니다. 20% 초과 시 주의 표시가 나타납니다.",
    )

if aging_rate > 20:
    st.warning(
        f"⚠️ 이 동네의 고령화율은 {aging_rate:.1f}%로 20%를 넘습니다. "
        "전체 인구 중 65세 이상 인구의 비중이 높은 지역입니다."
    )


# --------------------------------------------------
# 9. 인구 피라미드 가로 막대그래프
# --------------------------------------------------
fig = go.Figure()

# 남성 막대: 음수이므로 중앙의 왼쪽에 표시됩니다.
fig.add_trace(
    go.Bar(
        name="남성",
        y=ages,
        x=male_negative,
        orientation="h",
        marker_color=MALE_COLOR,
        hovertemplate=(
            "나이: %{y}<br>"
            "남성 인구: %{customdata:,}명"
            "<extra></extra>"
        ),
        customdata=male_values,
    )
)

# 여성 막대: 양수이므로 중앙의 오른쪽에 표시됩니다.
fig.add_trace(
    go.Bar(
        name="여성",
        y=ages,
        x=female_values,
        orientation="h",
        marker_color=FEMALE_COLOR,
        hovertemplate=(
            "나이: %{y}<br>"
            "여성 인구: %{x:,}명"
            "<extra></extra>"
        ),
    )
)

# x축을 남녀 대칭으로 설정합니다.
max_population = max(
    max(male_values, default=0),
    max(female_values, default=0),
    1,
)
axis_limit = max_population * 1.12

# 음수 눈금도 양수 인구처럼 읽히도록 절댓값 형식으로 표시합니다.
tick_step = max(1, int(np.ceil(axis_limit / 5)))
tick_values_positive = list(
    range(0, int(np.ceil(axis_limit)) + tick_step, tick_step)
)
tick_values = sorted(
    set(
        [-v for v in tick_values_positive if v != 0]
        + tick_values_positive
    )
)

fig.update_layout(
    title={
        "text": f"{selected_dong} 연령별 남녀 인구",
        "x": 0.5,
        "xanchor": "center",
    },
    barmode="overlay",
    bargap=0.12,
    height=1500,
    plot_bgcolor="#FFFFFF",
    paper_bgcolor=BACKGROUND,
    font=dict(
        family="Malgun Gothic, Apple SD Gothic Neo, sans-serif",
        color=TEXT_COLOR,
        size=12,
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="center",
        x=0.5,
    ),
    margin=dict(l=75, r=35, t=100, b=70),
)

fig.update_xaxes(
    title_text="인구 수 (명)",
    range=[-axis_limit, axis_limit],
    tickmode="array",
    tickvals=tick_values,
    ticktext=[f"{abs(v):,}" for v in tick_values],
    zeroline=True,
    zerolinewidth=2,
    zerolinecolor="#B8A99A",
    gridcolor="#F0E7DE",
)

# 중요!
# 나이 라벨을 0세부터 100세 이상까지 순서 그대로 지정합니다.
# 이 목록을 그대로 categoryarray에 넣으면 0세가 맨 아래,
# 100세 이상이 맨 위에 표시됩니다.
fig.update_yaxes(
    title_text="나이",
    type="category",
    categoryorder="array",
    categoryarray=ages,
    tickmode="array",
    tickvals=ages,
    ticktext=ages,
    showgrid=True,
    gridcolor="#F7F0E8",
)

st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------
# 10. 그래프 아래 자동 설명
# --------------------------------------------------
# 아이(0~14세) 비율과 어르신(65세 이상) 비율을 비교해
# 동네의 연령 구성을 한 줄로 설명합니다.
if total_population == 0:
    insight = "인구 자료가 없어 이 동네의 연령 구성을 비교하기 어렵습니다."
elif child_rate > aging_rate:
    insight = (
        f"🧒 이 동네는 아이(0~14세) 비율이 {child_rate:.1f}%로 "
        f"어르신(65세 이상) 비율 {aging_rate:.1f}%보다 높아, "
        "상대적으로 아이가 많은 편입니다."
    )
elif aging_rate > child_rate:
    insight = (
        f"👵 이 동네는 어르신(65세 이상) 비율이 {aging_rate:.1f}%로 "
        f"아이(0~14세) 비율 {child_rate:.1f}%보다 높아, "
        "상대적으로 어르신이 많은 편입니다."
    )
else:
    insight = (
        f"🧑‍🤝‍🧑 이 동네는 아이(0~14세)와 어르신(65세 이상)의 "
        f"비율이 각각 {child_rate:.1f}%로 같습니다."
    )

st.markdown("### 💬 이 동네는 아이가 많은 편인가요, 어르신이 많은 편인가요?")
st.markdown(
    f'<div class="insight">{insight}</div>',
    unsafe_allow_html=True,
)


# --------------------------------------------------
# 11. 연령별 인구 표 (필요하면 펼쳐 보기)
# --------------------------------------------------
with st.expander("📋 연령별 남녀 인구 표 보기"):
    detail_df = pd.DataFrame(
        {
            "나이": ages,
            "남성 인구": male_values,
            "여성 인구": female_values,
            "전체 인구": age_totals,
        }
    )

    st.dataframe(
        detail_df,
        hide_index=True,
        use_container_width=True,
    )

st.caption(
    f"기준 연도: {latest_year}년 · "
    "자료 출처: 제공된 전국 읍·면·동 인구 CSV"
)

st.markdown(
    '<div class="footer">동네의 인구 구성을 데이터로 살펴봅니다 🧡</div>',
    unsafe_allow_html=True,
)
