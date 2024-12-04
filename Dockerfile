FROM continuumio/miniconda3

RUN conda install -c conda-forge requests psycopg

COPY dist/artemis_data_collector-*-py3-none-any.whl .

RUN python -m pip install artemis_data_collector-*-py3-none-any.whl
RUN rm artemis_data_collector-*-py3-none-any.whl

CMD ["artemis_data_collector"]
