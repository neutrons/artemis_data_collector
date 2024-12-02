--
-- PostgreSQL database dump
--

-- Dumped from database version 14.12 (Debian 14.12-1.pgdg120+1)
-- Dumped by pg_dump version 14.5

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: report_statusqueue; Type: TABLE; Schema: public; Owner: workflow
--

CREATE TABLE public.report_statusqueue (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    is_workflow_input boolean NOT NULL
);


ALTER TABLE public.report_statusqueue OWNER TO workflow;

--
-- Name: report_statusqueue_id_seq; Type: SEQUENCE; Schema: public; Owner: workflow
--

CREATE SEQUENCE public.report_statusqueue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.report_statusqueue_id_seq OWNER TO workflow;

--
-- Name: report_statusqueue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: workflow
--

ALTER SEQUENCE public.report_statusqueue_id_seq OWNED BY public.report_statusqueue.id;


--
-- Name: report_statusqueue id; Type: DEFAULT; Schema: public; Owner: workflow
--

ALTER TABLE ONLY public.report_statusqueue ALTER COLUMN id SET DEFAULT nextval('public.report_statusqueue_id_seq'::regclass);


--
-- Name: report_statusqueue report_statusqueue_name_key; Type: CONSTRAINT; Schema: public; Owner: workflow
--

ALTER TABLE ONLY public.report_statusqueue
    ADD CONSTRAINT report_statusqueue_name_key UNIQUE (name);


--
-- Name: report_statusqueue report_statusqueue_pkey; Type: CONSTRAINT; Schema: public; Owner: workflow
--

ALTER TABLE ONLY public.report_statusqueue
    ADD CONSTRAINT report_statusqueue_pkey PRIMARY KEY (id);


--
-- Name: report_statusqueue_name_acb47977_like; Type: INDEX; Schema: public; Owner: workflow
--

CREATE INDEX report_statusqueue_name_acb47977_like ON public.report_statusqueue USING btree (name varchar_pattern_ops);


--
-- PostgreSQL database dump complete
--
