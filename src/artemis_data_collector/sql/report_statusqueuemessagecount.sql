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
-- Name: report_statusqueuemessagecount; Type: TABLE; Schema: public; Owner: workflow
--

CREATE TABLE public.report_statusqueuemessagecount (
    id integer NOT NULL,
    queue_id integer NOT NULL,
    message_count integer NOT NULL,
    created_on timestamp with time zone NOT NULL
);


ALTER TABLE public.report_statusqueuemessagecount OWNER TO workflow;

--
-- Name: report_statusqueuemessagecount_id_seq; Type: SEQUENCE; Schema: public; Owner: workflow
--

CREATE SEQUENCE public.report_statusqueuemessagecount_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.report_statusqueuemessagecount_id_seq OWNER TO workflow;

--
-- Name: report_statusqueuemessagecount_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: workflow
--

ALTER SEQUENCE public.report_statusqueuemessagecount_id_seq OWNED BY public.report_statusqueuemessagecount.id;


--
-- Name: report_statusqueuemessagecount id; Type: DEFAULT; Schema: public; Owner: workflow
--

ALTER TABLE ONLY public.report_statusqueuemessagecount ALTER COLUMN id SET DEFAULT nextval('public.report_statusqueuemessagecount_id_seq'::regclass);


--
-- Name: report_statusqueuemessagecount report_statusqueuemessagecount_pkey; Type: CONSTRAINT; Schema: public; Owner: workflow
--

ALTER TABLE ONLY public.report_statusqueuemessagecount
    ADD CONSTRAINT report_statusqueuemessagecount_pkey PRIMARY KEY (id);


--
-- Name: report_statusqueuemessagecount_queue_id_6b0ea71c; Type: INDEX; Schema: public; Owner: workflow
--

CREATE INDEX report_statusqueuemessagecount_queue_id_6b0ea71c ON public.report_statusqueuemessagecount USING btree (queue_id);


--
-- Name: report_statusqueuemessagecount report_statusqueueme_queue_id_6b0ea71c_fk_report_st; Type: FK CONSTRAINT; Schema: public; Owner: workflow
--

ALTER TABLE ONLY public.report_statusqueuemessagecount
    ADD CONSTRAINT report_statusqueueme_queue_id_6b0ea71c_fk_report_st FOREIGN KEY (queue_id) REFERENCES public.report_statusqueue(id) DEFERRABLE INITIALLY DEFERRED;


--
-- PostgreSQL database dump complete
--
