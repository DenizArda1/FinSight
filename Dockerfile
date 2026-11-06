FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home finsight \
    && mkdir -p financial_data logs/runs reports \
    && chown -R finsight:finsight /app
COPY --chown=finsight:finsight src ./src
COPY --chown=finsight:finsight configs ./configs
USER finsight
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"
CMD ["python", "-m", "streamlit", "run", "src/ui.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--browser.gatherUsageStats", "false"]
