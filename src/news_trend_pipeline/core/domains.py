from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainDefinition:
    id: str
    label: str
    query_keywords: tuple[str, ...]


DOMAIN_DEFINITIONS: tuple[DomainDefinition, ...] = (
    DomainDefinition(
        id="ai_tech",
        label="AI·테크",
        query_keywords=(
            "AI",
            "생성형 AI",
            "GPT",
            "LLM",
            "OpenAI",
            "Anthropic",
            "Claude",
            "엔비디아",
            "반도체",
            "AI 반도체",
            "HBM",
            "삼성전자",
            "TSMC",
            "로봇",
            "로보틱스",
            "자율주행",
            "클라우드",
            "데이터센터",
            "스타트업",
            "빅테크",
        ),
    ),
    DomainDefinition(
        id="economy_finance",
        label="경제·금융",
        query_keywords=(
            "기준금리",
            "인플레이션",
            "환율",
            "원달러",
            "코스피",
            "코스닥",
            "증시",
            "미국 증시",
            "연준",
            "한국은행",
            "부동산",
            "가계부채",
            "수출",
            "무역수지",
            "실적",
            "기업공개",
            "채권",
            "유가",
            "관세",
            "경기침체",
        ),
    ),
    DomainDefinition(
        id="politics_policy",
        label="정치·정책",
        query_keywords=(
            "대통령실",
            "국회",
            "정부조직",
            "예산안",
            "추경",
            "여당",
            "야당",
            "총선",
            "지방선거",
            "외교",
            "안보",
            "국방",
            "검찰",
            "사법개혁",
            "교육정책",
            "부동산 정책",
            "세제 개편",
            "복지정책",
            "의료정책",
            "노동정책",
        ),
    ),
    DomainDefinition(
        id="entertainment_culture",
        label="엔터·문화",
        query_keywords=(
            "K팝",
            "아이돌",
            "콘서트",
            "팬미팅",
            "넷플릭스",
            "OTT",
            "드라마",
            "영화",
            "박스오피스",
            "예능",
            "웹툰",
            "게임",
            "e스포츠",
            "뮤지컬",
            "전시",
            "축제",
            "BTS",
            "블랙핑크",
            "뉴진스",
            "한류",
        ),
    ),
)

DOMAIN_LABELS = {domain.id: domain.label for domain in DOMAIN_DEFINITIONS}

