FROM ghcr.io/prefix-dev/pixi:0.55.0-bookworm-slim


COPY pixi.lock .
COPY pyproject.toml .
RUN pixi install --locked -e deploy

COPY dist/artemis_data_collector-*-py3-none-any.whl .
RUN pixi run -e deploy python -m pip install artemis_data_collector-*-py3-none-any.whl
RUN rm artemis_data_collector-*-py3-none-any.whl

CMD ["pixi", "run", "-e", "deploy", "artemis_data_collector"]
