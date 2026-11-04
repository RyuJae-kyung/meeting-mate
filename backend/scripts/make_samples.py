"""시연용 샘플 회의 자료(PDF/DOCX/PPTX/TXT) 생성: python scripts/make_samples.py"""
import io
from pathlib import Path

import docx
import pymupdf
from pptx import Presentation

OUT = Path(__file__).resolve().parents[2] / "samples"
OUT.mkdir(exist_ok=True)

pdf = pymupdf.open()
pages = [
    ["스마트팩토리 MES-ERP 연동 프로젝트 계획서", "", "1. 배경", "현재 생산 실적은 MES에 기록되지만 ERP에는 매일 수기로 입력되고 있다.",
     "이로 인해 재고와 원가 데이터가 하루 이상 지연되며 입력 오류가 월 평균 30건 발생한다.", "", "2. 목표",
     "MES 생산 실적을 API Gateway를 통해 ERP로 실시간 전송한다.", "KPI: 데이터 정합성 99.5% 이상, 입력 지연 10분 이내."],
    ["3. 범위 및 일정", "1차 범위: 생산 실적, 자재 투입, 불량 데이터 연동.", "2차 범위(검토 중): 설비 IoT 센서 데이터 연동.",
     "PoC 2주 → 개발 6주 → QA 2주 → 오픈 (12월 말 목표).", "", "4. 예산 및 리스크", "예상 예산은 1억 2천만원이며 외부 SI 인력 2명을 포함한다.",
     "리스크: ERP 벤더의 API 제공 일정이 확정되지 않았다. SLA 협의가 필요하다."],
]
for lines in pages:
    p = pdf.new_page()
    y = 72
    for line in lines:
        p.insert_text((56, y), line, fontname="korea", fontsize=13 if y == 72 else 10)
        y += 22
pdf.set_metadata({"title": "스마트팩토리 MES-ERP 연동 프로젝트 계획서"})
(OUT / "MES-ERP_연동계획서.pdf").write_bytes(pdf.tobytes())

d = docx.Document()
d.add_heading("현업 요구사항 정의서", 1)
for t in ["생산팀은 작업 지시 변경 사항이 ERP에도 즉시 반영되기를 요구한다.",
          "구매팀은 자재 재고가 안전재고 이하일 때 알림을 받기를 원한다. SCM 시스템과의 연계 여부는 미정이다.",
          "재무팀은 월 마감 시 원가 데이터가 자동으로 집계되기를 요구한다."]:
    d.add_paragraph(t)
tbl = d.add_table(rows=3, cols=3)
for r, row in enumerate([["요구 ID", "내용", "우선순위"], ["REQ-01", "생산 실적 실시간 연동", "상"], ["REQ-02", "재고 부족 알림", "중"]]):
    for c, v in enumerate(row):
        tbl.cell(r, c).text = v
buf = io.BytesIO(); d.save(buf); (OUT / "요구사항정의서.docx").write_bytes(buf.getvalue())

prs = Presentation()
for title, body in [("MES-ERP 연동 킥오프", "회의 목적: 범위·일정·예산 합의"),
                    ("기술 구성안", "MES → API Gateway → ERP\nREST API + 배치 보정\nSSO 기반 인증"),
                    ("결정 필요 사항", "2차 범위 포함 여부\nSI 인력 투입 시점\nERP 벤더 SLA 조건")]:
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = title
    s.placeholders[1].text = body
buf = io.BytesIO(); prs.save(buf); (OUT / "킥오프_발표자료.pptx").write_bytes(buf.getvalue())

(OUT / "사전메모.txt").write_text("사전 메모\n\n영업팀: 주요 고객사 A사가 납기 정보를 실시간으로 받기를 원함. 계약 갱신이 내년 1월.\n\n"
                                  "IT팀: 기존 ERP 커스터마이징 이력이 많아 영향도 분석 필요.", encoding="utf-8")
print("samples written to", OUT)
