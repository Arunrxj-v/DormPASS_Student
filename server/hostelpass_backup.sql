--
-- PostgreSQL database dump
--

\restrict em8d2PDjgNpzrDl70uYTVTtc4cebRx2PAZCrWXs6PznUvaaUsj97WujWeluwMhE

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

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
-- Name: account_activation_tokens; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.account_activation_tokens (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_by uuid
);


ALTER TABLE public.account_activation_tokens OWNER TO hostelpass;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO hostelpass;

--
-- Name: attendance_attempts; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.attendance_attempts (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    outcome character varying(16) NOT NULL,
    rejection_code character varying(48),
    distance_m double precision,
    accuracy_m double precision
);


ALTER TABLE public.attendance_attempts OWNER TO hostelpass;

--
-- Name: attendance_records; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.attendance_records (
    id uuid NOT NULL,
    reference character varying(32) NOT NULL,
    student_id uuid NOT NULL,
    hostel_id uuid,
    attendance_date date NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    outcome character varying(24) NOT NULL,
    distance_m double precision,
    accuracy_m double precision,
    face_similarity double precision,
    liveness_score double precision,
    liveness_method character varying(48),
    gate character varying(48)
);


ALTER TABLE public.attendance_records OWNER TO hostelpass;

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.audit_logs (
    id uuid NOT NULL,
    actor_user_id uuid,
    actor_label character varying(64),
    action character varying(64) NOT NULL,
    target_type character varying(32),
    target_id character varying(64),
    details json,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.audit_logs OWNER TO hostelpass;

--
-- Name: face_enrollments; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.face_enrollments (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    embedding bytea NOT NULL,
    embedding_dim integer NOT NULL,
    model_version character varying(64) NOT NULL,
    quality json,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.face_enrollments OWNER TO hostelpass;

--
-- Name: hostels; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.hostels (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    block character varying(32),
    anchor_label character varying(128),
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    permitted_radius_m double precision NOT NULL,
    max_location_accuracy_m double precision NOT NULL,
    boundary_policy character varying(32) NOT NULL,
    timezone character varying(64) NOT NULL,
    window_start character varying(5) NOT NULL,
    window_end character varying(5) NOT NULL,
    require_liveness boolean NOT NULL,
    face_match_threshold double precision NOT NULL,
    warden_name character varying(128),
    warden_extension character varying(16),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.hostels OWNER TO hostelpass;

--
-- Name: revoked_tokens; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.revoked_tokens (
    id uuid NOT NULL,
    jti character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.revoked_tokens OWNER TO hostelpass;

--
-- Name: rooms; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.rooms (
    id uuid NOT NULL,
    hostel_id uuid NOT NULL,
    identifier character varying(32) NOT NULL,
    capacity integer,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.rooms OWNER TO hostelpass;

--
-- Name: students; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.students (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    student_id character varying(32) NOT NULL,
    name character varying(128) NOT NULL,
    department character varying(128),
    cohort character varying(64),
    room character varying(32),
    hostel_id uuid,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    email character varying(254),
    enrollment_status character varying(32) DEFAULT 'created'::character varying NOT NULL
);


ALTER TABLE public.students OWNER TO hostelpass;

--
-- Name: users; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    username character varying(64) NOT NULL,
    password_hash character varying(128) NOT NULL,
    role character varying(16) NOT NULL,
    account_status character varying(16) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.users OWNER TO hostelpass;

--
-- Name: warden_hostels; Type: TABLE; Schema: public; Owner: hostelpass
--

CREATE TABLE public.warden_hostels (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    hostel_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.warden_hostels OWNER TO hostelpass;

--
-- Data for Name: account_activation_tokens; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.account_activation_tokens (id, user_id, token_hash, created_at, expires_at, used_at, created_by) FROM stdin;
61f1ad65-58d6-4110-aec2-cea312f0c2e9	307eb069-84c1-44d1-a9ea-02c537121a86	af58919b33d39ee99da850c899c06706dceac2b4e68e70e315c3c3f49c415888	2026-10-13 17:24:06.563154+00	2026-10-20 17:24:06.563154+00	\N	\N
5d06863d-9b16-442a-89ed-62caeb8463c1	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	6ea19b31ad3d86e4782883638a9741edf11f654432d94360e84a7ed06996fc4e	2026-10-13 17:24:44.088016+00	2026-10-20 17:24:44.088016+00	2026-10-13 17:24:44.377842+00	\N
a9fe2f2d-036e-4e0c-b528-6955afa0fe93	8da3adcb-c78c-4230-a56e-8b584ed3f655	705c553bbc23e00cfe5f89101a625cc4ce4a2723e537bd1647988438fcf55558	2026-10-14 11:40:04.235998+00	2026-10-21 11:40:04.235998+00	2026-10-14 11:41:09.892806+00	19a59c24-666b-4d5d-ab19-da3c4d805970
a325511e-db8e-4c7b-8ef2-c6a21ee0b7ca	8da3adcb-c78c-4230-a56e-8b584ed3f655	1892d1b3cffe2c910f0655ef148f64b16fc9dec8d83ed9b9642be5bf979af2cc	2026-10-14 11:41:10.892806+00	2026-10-21 11:41:10.892806+00	2026-10-14 12:19:26.350267+00	19a59c24-666b-4d5d-ab19-da3c4d805970
db83a083-b492-4592-81a7-afe8afe46116	8da3adcb-c78c-4230-a56e-8b584ed3f655	9bf7bbdd71f2e21b268fbad35d028f373795e0ae06440c152f970dfcd252ac1b	2026-10-14 12:19:27.350267+00	2026-10-21 12:19:27.350267+00	2026-10-14 12:20:49.876218+00	19a59c24-666b-4d5d-ab19-da3c4d805970
909b2920-4fa4-49d0-9bdd-9d3d33600c49	8da3adcb-c78c-4230-a56e-8b584ed3f655	394fa0509bae2b2e82b69392dd1b237ec506b1759c666cdcd8c37e9d69d513af	2026-10-14 12:20:50.876218+00	2026-10-21 12:20:50.876218+00	2026-10-14 12:26:38.056455+00	19a59c24-666b-4d5d-ab19-da3c4d805970
9e43da16-e54c-4af9-8be7-17934541a0a8	8da3adcb-c78c-4230-a56e-8b584ed3f655	39fb96f336715e0af7bd4e7ef15df8d5ffba7c6d3a645f74327d69c046afe0fd	2026-10-14 12:26:39.056455+00	2026-10-21 12:26:39.056455+00	2026-10-14 12:27:15.84907+00	19a59c24-666b-4d5d-ab19-da3c4d805970
7c1bdd83-e9c3-49aa-b4f9-7aab8bc81e58	8da3adcb-c78c-4230-a56e-8b584ed3f655	bfd34f723c033c960a08f42f543d13cd2a45ba41b0afbc01eb96b563140301ff	2026-10-14 12:27:16.84907+00	2026-10-21 12:27:16.84907+00	2026-10-14 12:27:46.509199+00	19a59c24-666b-4d5d-ab19-da3c4d805970
61546ff9-069b-4ffa-ae64-d86bacf16d25	8da3adcb-c78c-4230-a56e-8b584ed3f655	e784c660e4d36eb3d5b818fce730c2738daff63da715207d7ed64bf0f8f331d3	2026-10-14 12:27:47.509199+00	2026-10-21 12:27:47.509199+00	2026-10-14 12:28:17.502106+00	19a59c24-666b-4d5d-ab19-da3c4d805970
96b85ce4-4b53-4689-8249-7d3fb191e1e1	8da3adcb-c78c-4230-a56e-8b584ed3f655	cbf0a8fbb6c2efb141d2888298a9f68d79e53898cb0b7a05f17f1f5677654231	2026-10-14 12:28:18.502106+00	2026-10-21 12:28:18.502106+00	\N	19a59c24-666b-4d5d-ab19-da3c4d805970
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.alembic_version (version_num) FROM stdin;
0003_rooms
\.


--
-- Data for Name: attendance_attempts; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.attendance_attempts (id, student_id, created_at, outcome, rejection_code, distance_m, accuracy_m) FROM stdin;
80dfa21a-9eb9-4a41-9701-bda629151193	12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	2026-10-13 13:23:13.774554+00	accepted	\N	2.473834483861918	4
4f3c2f1f-6866-40d1-a614-10f5c16e39bd	12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	2026-10-13 13:23:13.799239+00	rejected	duplicate_attendance	2.473834483861918	4
2c5d93fa-8090-4e22-a055-b5cb4d1cec0a	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	2026-10-13 13:23:14.079268+00	rejected	outside_geofence	14307.090489372553	5
799306f4-18af-40a1-b87e-53c419fb3895	12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	2026-10-13 13:57:56.852049+00	rejected	attendance_window_closed	\N	5
067cf602-7595-4dac-bc11-4a0f696ebf99	12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	2026-10-13 14:42:16.36856+00	rejected	attendance_window_closed	\N	8
f556646e-ecc9-4a00-a911-e1bff76d69e1	12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	2026-10-13 14:42:16.376881+00	rejected	attendance_window_closed	\N	8
37fb2bbf-ead8-426f-9a90-24cf80ead9fe	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	2026-10-13 15:12:19+00	rejected	outside_geofence	1123.0687591099936	12
8cf21ac6-3e88-49df-be84-79901cc5937e	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	2026-10-13 15:12:19+00	rejected	location_stale	\N	12
59323110-adff-41a0-8ad4-3c8768601e9b	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	2026-10-13 15:12:19+00	rejected	liveness_failed	11.11949266442996	12
3c512c3a-1846-42b8-b38b-1bb465a25bd6	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	2026-10-13 15:12:19+00	rejected	liveness_failed	11.11949266442996	12
32cd3bb0-b3d8-4f0e-bb5f-a250a36997bd	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	2026-10-13 15:12:19+00	accepted	\N	11.11949266442996	12
8aa18b1c-bb5e-466b-90b1-cdf69656215e	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	2026-10-13 15:12:19+00	rejected	duplicate_attendance	11.11949266442996	12
0b8f34d0-54d4-4c8c-92c2-4f8f0aec510f	12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	2026-10-13 15:12:19+00	rejected	face_mismatch	0	12
\.


--
-- Data for Name: attendance_records; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.attendance_records (id, reference, student_id, hostel_id, attendance_date, recorded_at, outcome, distance_m, accuracy_m, face_similarity, liveness_score, liveness_method, gate) FROM stdin;
eb684db0-7327-4bea-89f5-80f72f153304	HP-2026-1013-1853	12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13	2026-10-13 13:23:13.766683+00	verified	2.473834483861918	4	0.9999999999999998	0.012	antispoof_model_v1	\N
f9e357f3-de64-45f3-a898-d413f233af69	HP-2026-1013-2042	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13	2026-10-13 15:12:19+00	verified	11.11949266442996	12	0.9999999999999999	0.007	antispoof_model_v1	\N
\.


--
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.audit_logs (id, actor_user_id, actor_label, action, target_type, target_id, details, created_at) FROM stdin;
d5b7f023-5fe7-4450-9b28-d1f465bd1ae3	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	hostel.update	hostel	95bb0f53-1423-4f15-b2f4-f0f916d761eb	{"window_start": "00:00", "window_end": "23:59"}	2026-10-13 13:23:13.606646+00
62c3f702-d527-4947-b218-7ef5458f30f8	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	attendance.verify	attendance_record	eb684db0-7327-4bea-89f5-80f72f153304	{"date": "2026-10-13", "outcome": "verified", "reference": "HP-2026-1013-1853"}	2026-10-13 13:23:13.775864+00
66420011-482c-42a1-b3fc-1635b336459c	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	hostel.update	hostel	95bb0f53-1423-4f15-b2f4-f0f916d761eb	{"window_start": "20:30", "window_end": "22:30"}	2026-10-13 13:23:14.101151+00
ba457cfd-e286-45c2-b797-b344ab44a112	a72c25d0-0534-4d01-9073-b499cd60fb83	CS-2022-101	attendance.verify	attendance_record	f9e357f3-de64-45f3-a898-d413f233af69	{"date": "2026-10-13", "outcome": "verified", "reference": "HP-2026-1013-2042"}	2026-10-13 15:12:19+00
6b8a05ca-3382-4901-af6e-6c4738822816	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	student.create	student	CS-2026-900	{"name": "Test Device User", "hostel_id": null}	2026-10-13 15:17:00.656246+00
51c720af-ea5f-4ab5-afbe-eefece127f9d	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	student.update	student	CS-2026-900	{"hostel_id": "95bb0f53-1423-4f15-b2f4-f0f916d761eb"}	2026-10-13 15:18:54.531689+00
00e3e777-1d35-4cfa-989a-8fb57f1bfd67	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 16:50:22.115078+00
0c4d3ceb-bf70-4a5b-9036-ccb6a3195939	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 16:50:39.319001+00
84540bb7-1437-4ac5-8f97-7a76586f066c	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 16:51:02.915099+00
7aab5aa4-9d87-4c69-97fd-b6323151526e	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 17:24:06.533673+00
3e5c042e-c4db-4300-9ade-111bf2fb6dae	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 17:24:44.061456+00
f0505ce8-7c3f-4005-83c3-4df136716252	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	E2E-912282	auth.activate	student	0138674f-f622-4d78-8722-d3077f86dff9	{"method": "activation_token"}	2026-10-13 17:24:44.380936+00
29d36b41-bf51-4ab2-a255-5c656ee85eec	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	E2E-912282	auth.login	user	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	{"method": "activation", "role": "student"}	2026-10-13 17:24:44.382965+00
4ddaceb6-b32f-46b6-9af9-1170d0a489e9	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	E2E-912282	auth.login	user	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	{"method": "password", "role": "student"}	2026-10-13 17:24:44.65073+00
d48dd5ae-f80c-4931-a70f-ed6ba7f7dbb2	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	E2E-912282	auth.login	user	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	{"method": "password", "role": "student"}	2026-10-13 17:24:45.468634+00
225faab5-0ae9-4964-9200-ff40fdd82839	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 17:35:20.56282+00
ef4d87c3-fefd-49d0-b493-f511599d7edc	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	warden.create	user	e8e1a1ab-71c7-4390-8f04-ede4992d56dd	{"username": "e2e_warden", "hostels": []}	2026-10-13 17:35:20.936873+00
96c5b5d2-cdcd-4c6b-8a2c-1491ff526db9	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 17:35:38.160113+00
0fea6b71-aadb-4e0a-ab73-ace7024f234b	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 17:36:01.069016+00
390b2922-4e6a-4fe3-896d-2b8eb44cfb9c	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	warden.update	user	e8e1a1ab-71c7-4390-8f04-ede4992d56dd	{"username": "e2e_warden", "hostels": ["95bb0f53-1423-4f15-b2f4-f0f916d761eb"]}	2026-10-13 17:36:01.45632+00
548395f7-d72f-4fad-a96c-25299a2fa12a	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 16:50:21.845655+00
2d54f015-7e00-41cb-b6e3-aef333eba596	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 16:50:38.862505+00
f28f73f7-2efd-4f4c-bea2-f87cb8e9a13f	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 16:51:02.637738+00
46070091-bde4-42a4-a8f4-d4d34c0bfbe7	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 17:23:23.227888+00
fc64f990-ddf9-436d-8871-113e4e556a2a	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 17:23:48.912007+00
912e299c-6914-459c-b960-3ba7b2c74a6c	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	warden.update	user	e8e1a1ab-71c7-4390-8f04-ede4992d56dd	{"username": "e2e_warden", "account_status": "inactive"}	2026-10-13 17:36:01.822711+00
41f6a598-33f5-463f-af27-6369d7984895	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 17:36:02.44426+00
41c6e832-aa43-4bee-8258-58f1b4088da5	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 18:02:41.212279+00
477d1486-7b25-4b38-91bd-385c1c290b84	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 18:02:41.576468+00
fe057355-b1f1-4373-8443-ecb3dde1f6fd	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 18:02:42.738193+00
4c7b7444-994a-4170-bef9-ffa5201f06a0	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	auth.login	user	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	{"method": "password", "role": "student"}	2026-10-13 18:04:30.191334+00
a02cf9cc-7806-4836-a31b-6d6ea5f0eb48	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 20:34:35.332308+00
73b9bcd6-18df-4357-a19a-2287bb2cf08f	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	hostel.create	hostel	2c2712da-4655-4466-8127-62f50c0c589c	{"name": "Narmada Girls Hostel", "block": "C", "latitude": 12.972, "longitude": 79.159, "permitted_radius_m": 100.0}	2026-10-13 20:34:35.397168+00
2d117dca-8c67-4063-818d-38067914b41a	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	room.create	room	da05b4ba-cd71-42d6-8876-cca5cc2533b8	{"hostel_id": "2c2712da-4655-4466-8127-62f50c0c589c", "identifier": "101", "capacity": 2}	2026-10-13 20:34:35.448776+00
df37f5bf-ed18-456e-8c49-0fccdea74e17	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	room.create	room	9b3d43cd-26fa-4f14-9353-3c68e8c68476	{"hostel_id": "2c2712da-4655-4466-8127-62f50c0c589c", "identifier": "102", "capacity": 2}	2026-10-13 20:34:35.474094+00
d9d9432b-1f12-436c-b25b-0d94764e9b39	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	room.create	room	07622955-0930-4456-abb5-e2671a39a821	{"hostel_id": "2c2712da-4655-4466-8127-62f50c0c589c", "identifier": "201", "capacity": 2}	2026-10-13 20:34:35.499091+00
3e68fb3b-9c5b-4ef5-9df6-c2e2cf1aa803	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 20:34:52.389417+00
c186ecec-b41a-4f02-bc27-37f283bb834b	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	student.create	student	SMOKE-002	{"name": "Smoke Test Two", "email": "smoke-002@ceconline.edu", "hostel_id": "2c2712da-4655-4466-8127-62f50c0c589c", "room": "101", "status": "created"}	2026-10-13 20:34:52.703538+00
7c1117fe-33b6-4067-a10c-4d10de558032	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 20:58:13.594031+00
7d3b93cf-588f-4417-84c8-0ad8a314b03f	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 20:58:25.23068+00
00728043-99dc-4595-9660-13850c9ae975	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 20:58:38.201891+00
6514aaaf-04b4-40f1-8663-7902974796b7	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "refresh", "role": "admin"}	2026-10-13 20:58:49.927828+00
2f9ecd04-0396-40e3-a391-86c9534c86b8	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 22:41:06.749806+00
8fd65317-9247-4fd4-9347-730297b09353	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 22:41:07.016795+00
9219ec21-9c4f-409e-be3f-9ea5bd1baf14	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-13 22:41:37.20688+00
c63f5aab-e382-45fa-b821-d6e7126d3ca4	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-14 02:41:26.218927+00
ade6afc4-c38c-43d8-be89-5d27cac9ac09	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	admin.password_reset	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"source": "cli"}	2026-10-14 02:51:37.941407+00
04bc7638-37d4-4203-b611-a75db240fb5e	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-14 02:53:13.371614+00
30ebf26f-854b-45f6-b820-05b04d82773b	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	warden.delete	user	e8e1a1ab-71c7-4390-8f04-ede4992d56dd	{"username": "e2e_warden"}	2026-10-14 02:53:42.313048+00
aef0a305-fda4-4896-bac9-2194140bb6ec	\N	e2e_warden	auth.login	user	e8e1a1ab-71c7-4390-8f04-ede4992d56dd	{"method": "password", "role": "warden"}	2026-10-13 17:35:21.209585+00
481690dc-6d8a-4eff-8d28-089a302c8dee	\N	e2e_warden	auth.login	user	e8e1a1ab-71c7-4390-8f04-ede4992d56dd	{"method": "password", "role": "warden"}	2026-10-13 17:35:21.592197+00
358c07d5-3c01-435b-82cb-372182e607b1	\N	e2e_warden	auth.login	user	e8e1a1ab-71c7-4390-8f04-ede4992d56dd	{"method": "password", "role": "warden"}	2026-10-13 17:36:01.408954+00
f5a80945-3db4-458b-8b9d-599ce895db5f	\N	e2e_warden	auth.login	user	e8e1a1ab-71c7-4390-8f04-ede4992d56dd	{"method": "password", "role": "warden"}	2026-10-13 17:36:01.734389+00
885cc174-4e00-4b1b-a1ee-cca54f3b417c	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	warden.delete	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"username": "warden"}	2026-10-14 02:53:50.578978+00
b859e102-3875-48d2-9804-1ebc9befa236	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 17:24:05.159682+00
ad79fe3d-ad4c-4809-a06f-a49b8e139f6e	\N	warden	student.create	student	E2E-912244	{"name": "E2E Test Student", "email": "e2e-912244@ceconline.edu", "hostel_id": "95bb0f53-1423-4f15-b2f4-f0f916d761eb", "room": "401", "status": "created"}	2026-10-13 17:24:05.485774+00
9b0ec8d9-57ab-4074-aef6-c6b8932c1cb2	\N	warden	student.details_verified	student	bcb3393e-d857-446f-9482-66b1abfaece7	{"roll": "E2E-912244"}	2026-10-13 17:24:05.799807+00
79b58acf-a541-43a1-9189-11e477d7c539	\N	warden	face_enrollment.enroll	student	bcb3393e-d857-446f-9482-66b1abfaece7	{"roll": "E2E-912244", "model_version": "e2e_smoke_v1"}	2026-10-13 17:24:06.025533+00
1a9d1f59-8e2e-472f-bf79-b81345784578	\N	warden	student.provision	student	bcb3393e-d857-446f-9482-66b1abfaece7	{"roll": "E2E-912244"}	2026-10-13 17:24:06.562171+00
e9ae1553-90db-4fbb-9fb5-2e1a10e0dd37	\N	warden	student.activate_issue	student	bcb3393e-d857-446f-9482-66b1abfaece7	{"roll": "E2E-912244", "expires_at": "2026-10-20T17:24:06.563154+00:00"}	2026-10-13 17:24:06.588039+00
ffc6183b-6c0e-497e-b080-26a6aa3a92ca	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 17:24:42.906065+00
fc1cba51-6d7b-4397-b5db-fcb5a1a83499	\N	warden	student.create	student	E2E-912282	{"name": "E2E Test Student", "email": "e2e-912282@ceconline.edu", "hostel_id": "95bb0f53-1423-4f15-b2f4-f0f916d761eb", "room": "401", "status": "created"}	2026-10-13 17:24:43.194904+00
4c7a542e-b04d-4dbd-96a4-6002e22d4fc6	\N	warden	student.details_verified	student	0138674f-f622-4d78-8722-d3077f86dff9	{"roll": "E2E-912282"}	2026-10-13 17:24:43.47771+00
9a7da0db-a77f-4663-abdb-57bbbfc96e0b	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 18:02:42.45114+00
8440e5e6-5c7f-4b25-a40d-288b080ed183	\N	warden	face_enrollment.enroll	student	0138674f-f622-4d78-8722-d3077f86dff9	{"roll": "E2E-912282", "model_version": "e2e_smoke_v1"}	2026-10-13 17:24:43.526432+00
eb160fcf-2be5-452f-8d4b-c3612e591dac	\N	warden	student.provision	student	0138674f-f622-4d78-8722-d3077f86dff9	{"roll": "E2E-912282"}	2026-10-13 17:24:44.08692+00
a8073e6c-82e5-46bd-a575-f753cd652f3d	\N	warden	student.activate_issue	student	0138674f-f622-4d78-8722-d3077f86dff9	{"roll": "E2E-912282", "expires_at": "2026-10-20T17:24:44.088016+00:00"}	2026-10-13 17:24:44.090602+00
0b50f5db-fc37-45e0-9b91-48a388592af7	\N	warden	student.suspend	student	0138674f-f622-4d78-8722-d3077f86dff9	{"roll": "E2E-912282", "previous_status": "active"}	2026-10-13 17:24:44.659688+00
e9e439d3-4475-4485-b913-a8bc3d2de894	\N	warden	student.unsuspend	student	0138674f-f622-4d78-8722-d3077f86dff9	{"roll": "E2E-912282", "restored_status": "active"}	2026-10-13 17:24:45.197956+00
879a6fe4-6690-4626-83be-cda416330f63	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 18:47:53.16398+00
2ff0195c-f88c-4a55-bae9-89b171c097aa	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 19:09:23.873504+00
f3d38320-a828-4561-90d1-18bbe6501a3c	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 19:30:50.912431+00
1b9c3f7f-b7ee-41ad-86f6-862902850cce	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 20:58:38.215807+00
4efed40a-cf94-451a-94b8-701650430213	\N	warden	auth.login	user	c7e967ad-1703-4ecd-8ee9-c65b612d313c	{"method": "password", "role": "warden"}	2026-10-13 22:41:37.474271+00
249f5eca-0789-4b16-8edf-51618cd42d97	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.details_verified	student	9489036f-3932-4562-9e68-b2da9ecaf77d	{"roll": "chn23cse474"}	2026-10-14 02:56:37.060812+00
49212e31-d66f-4b02-aa30-428506d718b8	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	warden.create	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"username": "Suresh", "hostels": ["95bb0f53-1423-4f15-b2f4-f0f916d761eb"]}	2026-10-14 02:54:10.249152+00
ba0968bb-e727-4107-b9fe-c2d0dffbdcac	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 02:54:57.477632+00
7ab787c0-f91c-4a5f-ac07-02d7f80ac29c	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.create	student	chn23cse474	{"name": "Arunraj V", "email": "chn23cse474@ceconline.edu", "hostel_id": "95bb0f53-1423-4f15-b2f4-f0f916d761eb", "room": "10", "status": "created"}	2026-10-14 02:56:30.744063+00
bf1b1ffa-0cd3-4b7b-b6a0-ac2ead147b52	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	admin.password_reset	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"source": "cli"}	2026-10-14 05:34:25.057973+00
501f179d-1b00-4d8e-b751-6acab0aecfc2	52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	auth.login	user	52bb2d0b-30b0-475b-9080-0363ecdfbf82	{"method": "password", "role": "admin"}	2026-10-14 05:34:34.232192+00
c1ce8fbc-1a47-4635-8f2c-5ca41819d655	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 05:53:14.44149+00
f6807926-018d-40ec-94af-504042263df4	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.create	student	chn23cs039	{"name": "Anagha Omanakuttan", "email": "chn23cse440@ceconline.edu", "hostel_id": "95bb0f53-1423-4f15-b2f4-f0f916d761eb", "room": "12", "status": "created"}	2026-10-14 05:54:14.529526+00
efb9fe8e-a2f7-4ea4-809e-ab268ad87625	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.details_verified	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039"}	2026-10-14 05:54:20.03621+00
6ee00710-88a3-4bfb-a91e-6bf0ae4646fc	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 06:50:45.837654+00
ac2e3cb0-2af9-4241-9371-27ce713883ec	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 09:48:50.631433+00
b3708081-3217-446f-984f-6d0c48792afa	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.create	student	chn23cs333	{"name": "Anagha Omanakuttan", "email": "chn23cse464@ceconline.edu", "hostel_id": "95bb0f53-1423-4f15-b2f4-f0f916d761eb", "room": "11", "status": "created"}	2026-10-14 09:54:19.654941+00
24b68b94-f05e-4b38-934e-2d63a13f30c4	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.details_verified	student	c404b161-1499-4857-910d-b0e70ea06203	{"roll": "chn23cs333"}	2026-10-14 09:54:22.332558+00
b6577643-09d0-4430-bf24-4f383abe2c09	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 11:24:54.065834+00
8bc62a32-da42-4fcd-8a53-09b6dfe8f95d	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 11:26:19.221556+00
f4eef015-8872-4141-a082-6a6e5ad8d3ee	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 11:32:05.215182+00
5733d6e6-33ce-4bd6-a802-2aa63ce78f88	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	face_enrollment.enroll	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "model_version": "mobilefacenet_tflite_128_v1"}	2026-10-14 11:39:57.515692+00
d5056e6c-04c6-4878-9f5c-ae9d783dd106	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.provision	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039"}	2026-10-14 11:40:04.231906+00
6836253f-f614-46e7-9ebb-323a7f7c4b19	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.activate_issue	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "expires_at": "2026-10-21T11:40:04.235998+00:00"}	2026-10-14 11:40:04.254377+00
d5c93168-1266-4de7-88f4-04893cdfe65f	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.activate_issue	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "expires_at": "2026-10-21T11:41:10.892806+00:00"}	2026-10-14 11:41:10.899004+00
11f6606b-21e8-4350-a86f-3056b64dff71	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 12:19:27.298547+00
f0ea0fc4-e8e6-4563-9475-058cf4e15353	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.resend_activation	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "email_status": "failed"}	2026-10-14 12:19:27.39315+00
531be13c-ac2f-46eb-be05-39cd00d728ec	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 12:20:50.824592+00
f97c8495-35be-414b-8c6d-96658df89b36	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.resend_activation	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "email_status": "logged"}	2026-10-14 12:20:50.912094+00
36cbd4eb-c78b-4d36-8a80-56cd86834a25	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 12:26:39.010101+00
52522546-0f55-40c8-b226-fdb5f21cccdc	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.resend_activation	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "email_status": "failed"}	2026-10-14 12:26:39.189679+00
4bf9c0dc-91c8-4329-a541-684c57044006	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 12:27:16.816731+00
5c455895-886b-4c69-b04f-c6ad45e5cea8	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.resend_activation	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "email_status": "sent"}	2026-10-14 12:27:16.916374+00
f8226c60-e084-4bfd-879d-1850f8ed6aba	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 12:27:47.461692+00
d1e00559-3657-4dca-bb73-3666abf637e2	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.resend_activation	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "email_status": "sent"}	2026-10-14 12:27:47.549903+00
7a85e945-dce4-4e92-a2ea-27a6899c510c	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	auth.login	user	19a59c24-666b-4d5d-ab19-da3c4d805970	{"method": "password", "role": "warden"}	2026-10-14 12:28:18.451727+00
7d7dc816-cea7-4593-a881-6f894ab973bd	19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	student.resend_activation	student	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	{"roll": "chn23cs039", "email_status": "logged"}	2026-10-14 12:28:18.531316+00
\.


--
-- Data for Name: face_enrollments; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.face_enrollments (id, student_id, embedding, embedding_dim, model_version, quality, created_at, updated_at) FROM stdin;
6384e558-a719-4833-aae9-c2ea22c2ffab	12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	\\x67414141414142717a6b4e494b307957315955684549327142766d7630617a59574a4c4e4f566b37666a64507259756c52583259755375334e364c4244325133516849484c766c456748677374756f353951775f6c33324537354534356f314366514e5a6a7a6552715973614d54554a772d75696d6a586a6f6768706b465045726164714f43637934536e6e4f7a4d6d666e3038546d307977716a2d6833333464315777636a3259446949326e6b397657574c66717550566d4c6254336651716f6f375a437039626e42475173705843695a5538463554315f2d65434f79726a6e66746179302d442d43386b357339354933584b785652464e654d7058496c427130526b6d36384a4a54374c454a6a53746c796b4b415777554d655456477a636d4e6248693641395a73785355627771414d6c54524676784d4d5a5039364d49345f6b4f53306e7a2d64345454614c7779715a4b4250557032502d4c716c525a626354636a2d6e494665594b464e536767644175494959464b7261394a625a683663614471536e32575362575735354c4f6e5f56416f7552594d6c6e6b7078637a68702d675955326552566f6b6f5346495a43793168376856344a726c654e4c6e3550755079727469726979766b70466d6b67594e726b6371645f697a5f794e332d47556c6a725179455369445a55736754576e3965502d64425a534d7970314541574c4834575f4a4f3078367a56665678716230526a6a696f31524e74546439774d36485f715576575a7a48624e414656776f49594939476d71684c5372364143306d6b6f317a694b78304e3972735342577436315f6d6466455a504d6b30666f3967427677427276567957384e552d657475356842787676704432465275504664326d684b6f7a544d3952616955656f515769344363544149794c676d44727947644e456c7137524c70585577697648447a36666e64366252364451355051697033614350533355665a484b335a636244345a44695566376c6d2d334274654c4b6f724e316d696e54567979714b36715974746e414c434335624b4f734f702d31432d735930464c4b58	128	mobilefacenet_tflite_128_v1	null	2026-10-13 13:23:13.742084+00	2026-10-13 14:42:16.350124+00
e3a8bbba-c1f0-46fa-a1c2-2c0136f857ac	64c41ebd-f2df-43c5-8dee-4e3a67867fc8	\\x67414141414142717a6b5062666942496f754f6354355f7365734434714d4e376b704f536e4b4f78546830472d6e50663853706a644978322d6f51774f5947305f3855776667414544704a677163564d6e767633574433516a43774e524b427261766965772d6e6867794959484e793663454d7542564a784f5f7a465968675466375f2d36537139614d4741624a4b65794d6576455076324f387744566e6c3241343767796963595165444f7076484553506e6163333055306e5a4e714d537a37486a456831376e677352396e6e6e553566396a4657396d684a315672766956766d347548524d784468554e336f7a56343269745235314f343067467332797439366c695274334b6745793875633772437257713852464c4e78757a7050357a4c767267665f5a744f69636d473853515a715337306c5851395f6d6666565f32386872377036664a596b787555505f637235697875564d564f49536649486d5f357757706a786f3854626f39794f314b6c6a3549544d73672d6c563067503744757a7474566c567a3444797558313572425052436d676b37467259687253684a434f524a496e3762634f717362416b6549377858766b4a3858385643325f785f37507833754b494f492d316e5a524c523870623477364c36766a786b78724737587374614a42704d77524e3262734e585a425530645878694d3663623530464366397875726a48685230486c416c4a4b3874316d544868676c734b6c477a52595732786961634f4167564347546858363877534d354851487a6e7443734b672d656463696c5966355452736953747959784f5954704c445665384b6b4d56773557775750427544534674526d6577537347362d4f70537a67546a4b77686c74443277454b4e563352496b747a33323931477458465475324a4d336e544d455833633171356b616f5730627133584a544231793977515f7748366d3746467633346a67513147476936447134374678314c6d546a354943724b4746744a4d4c674d64687359677a5766396a5f4b4d4c49727372474659353638795a4f72416a7a73676c32374b6d4670644e2d49	128	mobilefacenet_tflite_128_v1	null	2026-10-13 15:12:19+00	2026-10-13 15:12:19+00
2355c9e0-03d7-4008-8000-87c24c94047d	bcb3393e-d857-446f-9482-66b1abfaece7	\\x67414141414142717a6d6b314b756e35663437306c3743654b6a5f354263753565744a317231666c37775273576d7176753948713059356d706c773465617579533561795249673750734239464c724f424277496a38786772414b5a434d58534f7972746a3354674c6c413538504a4762427067753564717631763951336a58355357476447306a49336e5153316f31574e305a5035336f2d6b527732382d715f536b6e4451443630394356337a76754a5847313568722d524d514854524c786d46626c4d323939797749624655736244793268677a6a646a6b6435375770485330533241747653565643546d384a53386b4f50506d7532724d725f4e485a617736496463334a6d7438625f6b4a354f445656704662505365315657546a41717643317954322d344f454c536c723348664a6565322d76334149544837775647544775494c616c74754b7678765273536f42543737387474666d3846657543354b52554a676b366a49664c4458655f6c44664330305047324d4163754c755f6a55634e784a415370703366595731354452744379743163644f6c6d6550396a68323170574f2d304553506646733574484336676c4838304b5863316f5575545a5a4b53616f4e566b544f61747034597278385061674871696d324c7452386c7447547267436d417a426c356e7242306f696e6166366357596b6f434c54526a6c48756557474e7244646d7571314e6478674a77755271343545674a5675354c794e635168364c6f6971425f387548696b4b6f4d6e59374c516f483938624b72566b4135384b51674b5672484e4676624f494c67624b5557657a79684d5f5a636e785841525945477a4a6338476f5a776a786c725a7268477364724179434c6a3566726a6755432d3838656e5f72522d7342476363434a59595a307142477864596944685446353338376f317165637230503251334c62756b4844644a7a6d57325956707655416e456f394d45745a52577a675757346b5277726e3435732d584d683567376a525a416370716b56374154563371666d3537465854435f55686c396f344b5455465f4a56316e79	128	e2e_smoke_v1	null	2026-10-13 17:24:06.019784+00	2026-10-13 17:24:06.019784+00
372ec797-c053-40b7-b62c-162b2678010f	0138674f-f622-4d78-8722-d3077f86dff9	\\x67414141414142717a6d6c624b3370456a37586f694e755332646936746a62584f495a784947726d624b766e61715f7053315257483547697052546a554378385a485f634f7741367474647a45524c58725a4e487733755869593252305a34434458546378666b624a302d75456968757939336e4b356c4a5477655274353446673641354e66546374435a59684b6a6b4d454e494362595a2d61345f77665744534b4757675758627250316b79655839577356365a4f4c7754492d4c4b326f344e66336859385865445a566c504e6b2d784949564f4456586179503654365959465f545a6b474674684356707636634f2d78453259593874787a357151716634336e386674653431373656783864306f7453733258745541513343687a7655796d42706f3266765032485631794567574e48774f7a6e4c4f6b353345686a6c676e326e774e474f534b4c70674c62746d48516e77486244537970446976706259354567415a55384e57746a5f58352d5f393033676d59645152517952514879524f6159757968364c4b524245685f4871726a4e6b62656b576e657164664a3058645f536d764975354c564a5234703766305a524d49496e43616a5a35356d46485635674a362d4334433854776c677839336166656b724a376e3346674347575163525f714a70614337554e3570504e6d493861304a4a39365951524461784e703839616c503542576b717a4f716f6a417272634e36374f785a67537a516d4e6a54556b37347953754f7762375362577447526454436f396470476e5562413767524a646c475f4359706b6f7a766f5f477953356a4732546f33764736694c4531314771422d6162654347345746616259653171544f36744c594f4131563831716d36754d536258516c4f67395a397967544a6c4b706e763978304c6c4c68386d6d4473793163615f436441396844795953504b355168636870646e42494e77384f63354e4d51734431355359564d61314877594a6431464a4c724c706d7661656166304752557152704651636d496f4a307450485757516a71697870435f57566e41783067585f79566a5a59	128	e2e_smoke_v1	null	2026-10-13 17:24:43.522376+00	2026-10-13 17:24:43.522376+00
bfa449da-4805-4581-9cc4-c057251260eb	b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	\\x67414141414142717a326f4e304a53373935745562543345554d4b584e4f776979566c2d687849596e31792d614e355a6a695868414b726b6d68687a4d676b5f535f4267465f6c514b47543073774845573631347470645132527165337338383575676e797848387678536f7552486f5842466f7755394b6563684b6b7250626c33384a6c3435384b5f3674514645644b5f515563546e447963474162744b4f7037654d506c6e694d50776a5a4567594b423233456a763932444b6555366275754b386f4361376c38554c5f704c506f4d5573484e4d504666754f38557a30727a4a654d4668594c6863654e42594e394f677133785a324d4b6f555561635932323546376f75734436464e706230764a3477336e682d615f373939664f307649526a70683353524a636744686c356e63735561553668714c726374304370424348503652337571746345664e426337365962303150546654634b564f6d7a35736d737070723764456a44484b4b467a6f37486878726230337a3643316d5a5f616e31454444546c774b4d4f41584231674e36487a3951575762766d505f35476a53474d426756594c7733374737784f306c422d36344f7459616f4a70574858506f33344d76664d416c4761704d4f4b777435723850683252795a6632484a4e3133415f62377972666a316650554e7061784353314c72666f6e346970684553396837354f72454d566d5a5661696779754675394854346e756f7365577370744b302d3849743576366f6c6b4866684a577465554e6c535569743757676341794d6f6f756a674169465f38323951783956576e62376e43523461784d3431754f33475f4e456c7741565438716d666441733755744c47565f5f5347694947526933773755434d434d33757958684148637239324242754243643356714f484e416b5754594d634334557a6c737a4530725979625a42767647586875733733587352464f55782d507277454b734d5779465f524b4f2d695748552d485f7655444e75764c78737554355f554362325a32646c383561443538596966723578725a5874516f784c306848597875416c	128	mobilefacenet_tflite_128_v1	null	2026-10-14 11:39:57.502709+00	2026-10-14 11:39:57.502709+00
\.


--
-- Data for Name: hostels; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.hostels (id, name, block, anchor_label, latitude, longitude, permitted_radius_m, max_location_accuracy_m, boundary_policy, timezone, window_start, window_end, require_liveness, face_match_threshold, warden_name, warden_extension, created_at, updated_at) FROM stdin;
95bb0f53-1423-4f15-b2f4-f0f916d761eb	Ganga Boys Hostel	B	Ganga Block B	12.9716	79.1585	120	50	conservative	Asia/Kolkata	20:30	22:30	t	0.75	Dr. K. Raman	204	2026-10-13 12:51:34.819734+00	2026-10-13 13:23:14.101766+00
2c2712da-4655-4466-8127-62f50c0c589c	Narmada Girls Hostel	C	Narmada Block C	12.972	79.159	100	40	conservative	Asia/Kolkata	20:30	22:30	t	0.75	\N	\N	2026-10-13 20:34:35.395696+00	2026-10-13 20:34:35.3957+00
\.


--
-- Data for Name: revoked_tokens; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.revoked_tokens (id, jti, expires_at, created_at) FROM stdin;
4745375d-d9f0-45b7-8a6d-e2c64c315993	86350e6ed1424988ad0e06c9ba3049b0	2026-10-14 11:54:54+00	2026-10-14 11:25:27.030164+00
\.


--
-- Data for Name: rooms; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.rooms (id, hostel_id, identifier, capacity, created_at, updated_at) FROM stdin;
da05b4ba-cd71-42d6-8876-cca5cc2533b8	2c2712da-4655-4466-8127-62f50c0c589c	101	2	2026-10-13 20:34:35.44593+00	2026-10-13 20:34:35.445934+00
9b3d43cd-26fa-4f14-9353-3c68e8c68476	2c2712da-4655-4466-8127-62f50c0c589c	102	2	2026-10-13 20:34:35.473636+00	2026-10-13 20:34:35.473637+00
07622955-0930-4456-abb5-e2671a39a821	2c2712da-4655-4466-8127-62f50c0c589c	201	2	2026-10-13 20:34:35.49863+00	2026-10-13 20:34:35.498632+00
\.


--
-- Data for Name: students; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.students (id, user_id, student_id, name, department, cohort, room, hostel_id, created_at, updated_at, email, enrollment_status) FROM stdin;
43e571ab-990d-4869-899c-5a6fc47efed8	7ccf63aa-2fcf-4c64-9118-5b8615a3b4a6	CS-2026-900	Test Device User	CSE	B.Tech 2026	\N	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13 15:17:00.658446+00	2026-10-13 15:18:54.533584+00	\N	active
12aa5b8b-2fac-46e7-864c-e3dc5dfe6340	ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	Rohan Sharma	Computer Science & Engg	3rd Year (B.Tech 22–26)	314	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13 12:51:35.065459+00	2026-10-13 16:46:39.627094+00	cs-2022-084@ceconline.edu	active
64c41ebd-f2df-43c5-8dee-4e3a67867fc8	a72c25d0-0534-4d01-9073-b499cd60fb83	CS-2022-101	Arjun Mehta	Computer Science & Engg	3rd Year (B.Tech 22–26)	315	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13 12:51:35.304917+00	2026-10-13 16:46:39.933561+00	cs-2022-101@ceconline.edu	active
941c054f-e2e5-4752-bde0-846dc8344323	16e145d6-99ec-4e39-aafb-0aa7c4fddaa4	CS-2022-132	Kabir Nair	Computer Science & Engg	3rd Year (B.Tech 22–26)	318	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13 16:46:40.701471+00	2026-10-13 16:46:40.70148+00	cs-2022-132@ceconline.edu	created
2c10c096-aa55-476f-8523-25d976fc6061	faf7c0e0-896d-4b65-a2c5-7240810a7986	CS-2022-117	Ishaan Verma	Computer Science & Engg	3rd Year (B.Tech 22–26)	316	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13 16:46:40.188148+00	2026-10-13 16:52:29.663103+00	cs-2022-117@ceconline.edu	details_verified
bcb3393e-d857-446f-9482-66b1abfaece7	307eb069-84c1-44d1-a9ea-02c537121a86	E2E-912244	E2E Test Student	\N	\N	401	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13 17:24:05.48759+00	2026-10-13 17:24:06.562515+00	e2e-912244@ceconline.edu	account_provisioned
0138674f-f622-4d78-8722-d3077f86dff9	7f3b04ab-04a3-492c-aeb4-6242aeff02ff	E2E-912282	E2E Test Student	\N	\N	401	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-13 17:24:43.196924+00	2026-10-13 17:24:45.201883+00	e2e-912282@ceconline.edu	active
056fafbd-ef1f-4fcf-a498-0931de3cb5c8	8630a444-6b7c-44d2-b99c-715d84f6f562	SMOKE-002	Smoke Test Two	\N	\N	101	2c2712da-4655-4466-8127-62f50c0c589c	2026-10-13 20:34:52.704442+00	2026-10-13 20:34:52.704443+00	smoke-002@ceconline.edu	created
9489036f-3932-4562-9e68-b2da9ecaf77d	56979ae5-0afe-4d98-a289-d255ae0a7264	chn23cse474	Arunraj V	Computer Science	2023-2027	10	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-14 02:56:30.745948+00	2026-10-14 02:56:37.063494+00	chn23cse474@ceconline.edu	details_verified
c404b161-1499-4857-910d-b0e70ea06203	88643b83-b496-444c-98e9-b8b5ea6c4421	chn23cs333	Anagha Omanakuttan	\N	\N	11	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-14 09:54:19.658786+00	2026-10-14 09:54:22.333924+00	chn23cse464@ceconline.edu	details_verified
b7d84f6f-ac8c-4925-a97d-5f04e81d98b7	8da3adcb-c78c-4230-a56e-8b584ed3f655	chn23cs039	Anagha Omanakuttan	\N	\N	12	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-14 05:54:14.530196+00	2026-10-14 11:40:04.23386+00	chn23cse440@ceconline.edu	account_provisioned
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.users (id, username, password_hash, role, account_status, created_at, updated_at) FROM stdin;
7ccf63aa-2fcf-4c64-9118-5b8615a3b4a6	CS-2026-900	$2b$12$HUc5.a2cULpzS19MyNX2tOb2gLgU224aVGFyG2hV.CemY9ZPS4KhC	student	active	2026-10-13 15:17:00.653998+00	2026-10-13 15:17:00.654003+00
ff5d15e6-8f15-4237-95cc-d3ba7d77d18f	CS-2022-084	$2b$12$lsoZ0KaJziWNgd/s2bpgpe5qiWU8QfzrkrxANpU6Aqc1Q4YAlRV.K	student	active	2026-10-13 12:51:35.055034+00	2026-10-13 16:52:29.146325+00
a72c25d0-0534-4d01-9073-b499cd60fb83	CS-2022-101	$2b$12$tnwSJoTrolqxWQ8MBmGrm.ap1wNozSE3sVaIlhU0gEnjV5LB84zWO	student	active	2026-10-13 12:51:35.300932+00	2026-10-13 16:52:29.417089+00
faf7c0e0-896d-4b65-a2c5-7240810a7986	CS-2022-117	$2b$12$i5QVi9dmwMfs2Me1DfOoN.y8M5woVr3yRXYlNQBHIIku8x.ABJJ5y	student	inactive	2026-10-13 16:46:40.178517+00	2026-10-13 16:52:29.658909+00
16e145d6-99ec-4e39-aafb-0aa7c4fddaa4	CS-2022-132	$2b$12$1oon2pKc2diMnlOl7.lroe3dTUbwGxA5AuOPW3DAKYyoWfP2KFS.i	student	inactive	2026-10-13 16:46:40.693479+00	2026-10-13 16:52:29.918735+00
307eb069-84c1-44d1-a9ea-02c537121a86	E2E-912244	$2b$12$WZAjxBtUwzbPvZz4yPVsm.h9EynznPZRoGKyUXtRsmAdQcogRNeCy	student	inactive	2026-10-13 17:24:05.480132+00	2026-10-13 17:24:05.480136+00
7f3b04ab-04a3-492c-aeb4-6242aeff02ff	E2E-912282	$2b$12$Ogapfy4Xi7X5K9AnYeUw3eiY.u5STRlhMVhxh8zZEWfpezgHpK2cm	student	active	2026-10-13 17:24:43.191322+00	2026-10-13 17:24:45.200256+00
8630a444-6b7c-44d2-b99c-715d84f6f562	SMOKE-002	$2b$12$7LNcwzCHO64Lzj7dVF/4PeXN.jKJqWtVc4Fdcsr3P.CGjD.iLqnb2	student	inactive	2026-10-13 20:34:52.701917+00	2026-10-13 20:34:52.701921+00
19a59c24-666b-4d5d-ab19-da3c4d805970	Suresh	$2b$12$KF6nyWH8eCuH5kRZyOnx2uOzN15qvj85kWZdXAQHFjWQk0GVe6fQq	warden	active	2026-10-14 02:54:10.247687+00	2026-10-14 02:54:10.247692+00
56979ae5-0afe-4d98-a289-d255ae0a7264	chn23cse474	$2b$12$j856fp8hXbGLes1JsOycMOk5A6n6xnSpDw.7i3imGCv26SvkdG59W	student	inactive	2026-10-14 02:56:30.742431+00	2026-10-14 02:56:30.742435+00
52bb2d0b-30b0-475b-9080-0363ecdfbf82	admin	$2b$12$XUuF.oh8ywKXT/8vWt/bWe.wxC90PuzyLp/9ehlaOOb1zaItw3.py	admin	active	2026-10-13 12:51:34.812523+00	2026-10-14 05:34:25.062793+00
8da3adcb-c78c-4230-a56e-8b584ed3f655	chn23cs039	$2b$12$0yCa3tlIwAtP8iSI95NpPe96fpeWdA56N66NJmGpaZ31bkpdQqgFm	student	inactive	2026-10-14 05:54:14.528118+00	2026-10-14 05:54:14.528122+00
88643b83-b496-444c-98e9-b8b5ea6c4421	chn23cs333	$2b$12$j8ftZ36WvWFKULu7Pmc6y.Gn6j1.jmmviY61sEvX8Fg6uvM.IHJxW	student	inactive	2026-10-14 09:54:19.648224+00	2026-10-14 09:54:19.648229+00
\.


--
-- Data for Name: warden_hostels; Type: TABLE DATA; Schema: public; Owner: hostelpass
--

COPY public.warden_hostels (id, user_id, hostel_id, created_at) FROM stdin;
7d760d12-a3aa-491d-ba71-16e162cdb0e2	19a59c24-666b-4d5d-ab19-da3c4d805970	95bb0f53-1423-4f15-b2f4-f0f916d761eb	2026-10-14 02:54:10.251639+00
\.


--
-- Name: account_activation_tokens account_activation_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.account_activation_tokens
    ADD CONSTRAINT account_activation_tokens_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: attendance_attempts attendance_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.attendance_attempts
    ADD CONSTRAINT attendance_attempts_pkey PRIMARY KEY (id);


--
-- Name: attendance_records attendance_records_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.attendance_records
    ADD CONSTRAINT attendance_records_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: face_enrollments face_enrollments_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.face_enrollments
    ADD CONSTRAINT face_enrollments_pkey PRIMARY KEY (id);


--
-- Name: face_enrollments face_enrollments_student_id_key; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.face_enrollments
    ADD CONSTRAINT face_enrollments_student_id_key UNIQUE (student_id);


--
-- Name: hostels hostels_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.hostels
    ADD CONSTRAINT hostels_pkey PRIMARY KEY (id);


--
-- Name: revoked_tokens revoked_tokens_jti_key; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.revoked_tokens
    ADD CONSTRAINT revoked_tokens_jti_key UNIQUE (jti);


--
-- Name: revoked_tokens revoked_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.revoked_tokens
    ADD CONSTRAINT revoked_tokens_pkey PRIMARY KEY (id);


--
-- Name: rooms rooms_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (id);


--
-- Name: students students_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_pkey PRIMARY KEY (id);


--
-- Name: students students_student_id_key; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_student_id_key UNIQUE (student_id);


--
-- Name: students students_user_id_key; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_user_id_key UNIQUE (user_id);


--
-- Name: account_activation_tokens uq_account_activation_token_hash; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.account_activation_tokens
    ADD CONSTRAINT uq_account_activation_token_hash UNIQUE (token_hash);


--
-- Name: attendance_records uq_attendance_reference; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.attendance_records
    ADD CONSTRAINT uq_attendance_reference UNIQUE (reference);


--
-- Name: attendance_records uq_attendance_student_date; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.attendance_records
    ADD CONSTRAINT uq_attendance_student_date UNIQUE (student_id, attendance_date);


--
-- Name: hostels uq_hostel_name_block; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.hostels
    ADD CONSTRAINT uq_hostel_name_block UNIQUE (name, block);


--
-- Name: rooms uq_room_hostel_identifier; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT uq_room_hostel_identifier UNIQUE (hostel_id, identifier);


--
-- Name: warden_hostels uq_warden_hostel; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.warden_hostels
    ADD CONSTRAINT uq_warden_hostel UNIQUE (user_id, hostel_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: warden_hostels warden_hostels_pkey; Type: CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.warden_hostels
    ADD CONSTRAINT warden_hostels_pkey PRIMARY KEY (id);


--
-- Name: ix_account_activation_tokens_token_hash; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE UNIQUE INDEX ix_account_activation_tokens_token_hash ON public.account_activation_tokens USING btree (token_hash);


--
-- Name: ix_account_activation_tokens_user_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_account_activation_tokens_user_id ON public.account_activation_tokens USING btree (user_id);


--
-- Name: ix_attendance_attempts_created_at; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_attendance_attempts_created_at ON public.attendance_attempts USING btree (created_at);


--
-- Name: ix_attendance_attempts_student_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_attendance_attempts_student_id ON public.attendance_attempts USING btree (student_id);


--
-- Name: ix_attendance_records_attendance_date; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_attendance_records_attendance_date ON public.attendance_records USING btree (attendance_date);


--
-- Name: ix_attendance_records_reference; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_attendance_records_reference ON public.attendance_records USING btree (reference);


--
-- Name: ix_attendance_records_student_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_attendance_records_student_id ON public.attendance_records USING btree (student_id);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_audit_logs_created_at; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);


--
-- Name: ix_face_enrollments_student_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_face_enrollments_student_id ON public.face_enrollments USING btree (student_id);


--
-- Name: ix_revoked_tokens_expires_at; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_revoked_tokens_expires_at ON public.revoked_tokens USING btree (expires_at);


--
-- Name: ix_revoked_tokens_jti; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_revoked_tokens_jti ON public.revoked_tokens USING btree (jti);


--
-- Name: ix_rooms_hostel_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_rooms_hostel_id ON public.rooms USING btree (hostel_id);


--
-- Name: ix_students_email; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE UNIQUE INDEX ix_students_email ON public.students USING btree (email);


--
-- Name: ix_students_enrollment_status; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_students_enrollment_status ON public.students USING btree (enrollment_status);


--
-- Name: ix_students_hostel_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_students_hostel_id ON public.students USING btree (hostel_id);


--
-- Name: ix_students_student_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_students_student_id ON public.students USING btree (student_id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: ix_warden_hostels_hostel_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_warden_hostels_hostel_id ON public.warden_hostels USING btree (hostel_id);


--
-- Name: ix_warden_hostels_user_id; Type: INDEX; Schema: public; Owner: hostelpass
--

CREATE INDEX ix_warden_hostels_user_id ON public.warden_hostels USING btree (user_id);


--
-- Name: account_activation_tokens account_activation_tokens_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.account_activation_tokens
    ADD CONSTRAINT account_activation_tokens_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: account_activation_tokens account_activation_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.account_activation_tokens
    ADD CONSTRAINT account_activation_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: attendance_attempts attendance_attempts_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.attendance_attempts
    ADD CONSTRAINT attendance_attempts_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE CASCADE;


--
-- Name: attendance_records attendance_records_hostel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.attendance_records
    ADD CONSTRAINT attendance_records_hostel_id_fkey FOREIGN KEY (hostel_id) REFERENCES public.hostels(id) ON DELETE SET NULL;


--
-- Name: attendance_records attendance_records_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.attendance_records
    ADD CONSTRAINT attendance_records_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE CASCADE;


--
-- Name: audit_logs audit_logs_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: face_enrollments face_enrollments_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.face_enrollments
    ADD CONSTRAINT face_enrollments_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE CASCADE;


--
-- Name: rooms rooms_hostel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_hostel_id_fkey FOREIGN KEY (hostel_id) REFERENCES public.hostels(id) ON DELETE CASCADE;


--
-- Name: students students_hostel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_hostel_id_fkey FOREIGN KEY (hostel_id) REFERENCES public.hostels(id) ON DELETE SET NULL;


--
-- Name: students students_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: warden_hostels warden_hostels_hostel_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.warden_hostels
    ADD CONSTRAINT warden_hostels_hostel_id_fkey FOREIGN KEY (hostel_id) REFERENCES public.hostels(id) ON DELETE CASCADE;


--
-- Name: warden_hostels warden_hostels_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: hostelpass
--

ALTER TABLE ONLY public.warden_hostels
    ADD CONSTRAINT warden_hostels_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict em8d2PDjgNpzrDl70uYTVTtc4cebRx2PAZCrWXs6PznUvaaUsj97WujWeluwMhE

