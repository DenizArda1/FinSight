"""Local Streamlit interface for the existing multi-agent MCP workflow."""

import asyncio
from pathlib import Path
import sys
from time import perf_counter

# Streamlit prepends the script directory. Keep src.* imports rooted at the
# project, so src/mcp cannot shadow the installed top-level mcp package.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path[:] = [
    str(PROJECT_ROOT),
    *(entry for entry in sys.path
      if Path(entry).resolve() not in (PROJECT_ROOT, SOURCE_ROOT)),
]

import streamlit as st

from src.agents.runtime import run_mcp_orchestrator
from src.cli import format_request_error
from src.reporting import DISCLAIMER, format_citation_links, save_report, source_financial_rows, split_research_note
from src.utils.utils import load_yaml
from src.verification.agent_answer import format_source_references
from src.verification.citations import SOURCE_REFERENCE


def show_sources(answer, evidence):
    references = format_source_references(answer, evidence)
    if not references:
        st.caption("Bu yanıt kaynaklı bir finansal bulgu içermiyor.")
        return
    cited = {int(number) for number in SOURCE_REFERENCE.findall(answer)}
    for source in evidence:
        if source["source_id"] not in cited or source.get("content_omitted"):
            continue
        source_id = source["source_id"]
        st.markdown(f'<span id="source-{source_id}"></span>', unsafe_allow_html=True)
        reference = format_source_references(answer, [source])
        st.markdown(reference.replace(f"[Source {source_id}]", f"**{source_id}.**").replace("\n", "\n\n"))
        result = source["result"]
        if source["tool"] == "search_filings":
            excerpts = [match.get("context", {}).get("text", match.get("text", ""))
                        for match in result.get("matches", [])]
        elif source["tool"] == "get_filing_section":
            excerpts = [result.get("text", "")]
        else:
            continue
        text = "\n\n".join(excerpt for excerpt in excerpts if excerpt)
        if text:
            with st.expander(f"Source {source['source_id']} — kaynak metni"):
                st.text(text)

def main():
    st.set_page_config(page_title="FinSight", page_icon="📊", layout="wide")
    st.title("FinSight")
    st.caption("Şirket raporları ve finansal veriler üzerinden kaynaklı araştırma")
    st.warning("Yatırım tavsiyesi değildir; eğitim amaçlı prototip.")

    with st.form("research"):
        ticker = st.selectbox("Şirket", ["Soruda belirteceğim", "AAPL", "MSFT", "AMZN", "NVDA"])
        question = st.text_area(
            "Sorun", placeholder="Apple'ın yerel verideki en son yıllık gelirini ve mali yılını söyle.",
            height=110,
        )
        st.caption("Sorunuzu istediğiniz dilde yazabilirsiniz. Yanıt sorunun dilini izler. Yerel veriler kullanılır; canlı piyasa verisi sunulmaz.")
        submitted = st.form_submit_button("Araştır", type="primary")

    if submitted:
        for key in ("research_result", "research_error", "export_path"):
            st.session_state.pop(key, None)
        if not question.strip():
            st.error("Lütfen bir araştırma sorusu yazın.")
        else:
            scoped_question = question.strip()
            if ticker != "Soruda belirteceğim":
                scoped_question += f"\nSelected company: {ticker}."
            started = perf_counter()
            with st.status("Kaynaklar inceleniyor ve yanıt kontrol ediliyor…", expanded=True) as status:
                st.write("Kaynak toplama ve yanıt doğrulama birkaç dakika sürebilir.")
                try:
                    settings = load_yaml(PROJECT_ROOT / "configs/settings.yaml")
                    result = asyncio.run(run_mcp_orchestrator(scoped_question, settings["llm"]))
                    st.session_state["research_result"] = {
                        "question": scoped_question, "result": result,
                        "elapsed_seconds": perf_counter() - started,
                    }
                    status.update(label="İşlem tamamlandı", state="complete", expanded=False)
                except Exception as error:
                    st.session_state["research_error"] = format_request_error(error)
                    status.update(label="İşlem tamamlanamadı", state="error", expanded=False)

    if st.session_state.get("research_error"):
        st.error("Yanıt oluşturulamadı. Ollama bağlantısını ve API erişimini kontrol edip yeniden deneyin.")
        with st.expander("Hata ayrıntısı"):
            st.text(st.session_state["research_error"])

    saved = st.session_state.get("research_result")
    if saved:
        result = saved["result"]
        st.caption(f"Yanıtlanan soru: {saved['question']}")
        st.caption(f"Süre: {saved['elapsed_seconds']:.1f} saniye")
        usage = result.get("usage")
        if usage:
            st.caption(f"Token: {usage['input_tokens'] + usage['output_tokens']:,} · "
                       f"Tahmini API maliyeti: ${usage['estimated_cost_usd']:.6f}")
        if result.get("trace_path"):
            with st.expander("Çalışma kaydı"):
                trace_path = Path(result["trace_path"])
                if trace_path.is_file():
                    st.download_button("Tanı kaydını indir", trace_path.read_text(encoding="utf-8"),
                                       file_name=trace_path.name, mime="application/json")
        if result.get("answer") and (result.get("verification") or {}).get("supported") is True:
            note, sources = st.columns([2, 1])
            with note:
                st.subheader("Araştırma notu")
                prose, details = split_research_note(result)
                st.markdown(format_citation_links(prose))
                if details:
                    with st.expander("Veri ve rapor ayrıntıları"):
                        st.markdown(format_citation_links(details))
                st.caption("Otomatik kontrol hataları kaçırabilir. Özetlerdeki iddiaları kaynak metinleriyle karşılaştırın.")
            with sources:
                st.subheader("Kaynaklar")
                show_sources(result["answer"], result.get("evidence", []))
            if st.button("Markdown olarak kaydet"):
                try:
                    st.session_state["export_path"] = str(save_report(saved["question"], result))
                except (OSError, ValueError) as error:
                    st.error(f"Rapor kaydedilemedi: {error}")
            if st.session_state.get("export_path"):
                report_path = Path(st.session_state["export_path"])
                st.success(f"Kaydedildi: reports/{report_path.name}")
                st.download_button("Raporu indir", report_path.read_text(encoding="utf-8"),
                                   file_name=report_path.name, mime="text/markdown")
        else:
            st.warning("Yanıt doğrulama kontrollerini geçemedi. Doğrulanmış bir araştırma notu oluşturulmadı.")
            rows, evidence = source_financial_rows(result)
            if rows:
                st.subheader("Kaynaklardan alınan finansal veriler")
                st.caption("Bu değerler araç çıktılarıdır. Modelin açıklaması doğrulanmadı; bu tablo tam araştırma notu değildir.")
                st.dataframe(rows, hide_index=True)
                references = " ".join(f"[Source {row['Kaynak']}]" for row in rows)
                with st.expander("Finansal verilerin kaynakları"):
                    st.markdown(format_source_references(references, evidence).replace("\n", "\n\n"))
            issues = (result.get("verification") or {}).get("issues", [])
            if issues:
                with st.expander("Kontrol sonucu"):
                    for issue in issues:
                        st.write(issue)
            if result.get("draft"):
                with st.expander("Doğrulanmamış taslağı göster"):
                    st.error("Bu taslak doğrulanmadı; hatalı veya eksik bilgiler içerebilir.")
                    st.markdown(result["draft"])

    st.divider()
    st.caption(DISCLAIMER)


if __name__ == "__main__":
    main()
