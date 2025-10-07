-- ===========================================================
-- JOB MIGRATION SCRIPT (AUTO-INCREMENT SAFE)
-- Source DB: kojobd
-- Target DB: kojobdnew
-- Description: Transfer selected jobs and related records
-- Date: 2025-10-06
-- ===========================================================

-- Define job IDs to transfer
SET @job_ids := '22549,22552,22559,22560,22561,22565,22567,22569,22576,22578,22579,22580';

-- ===========================================================
-- STEP 1: CONTACTS
-- ===========================================================
INSERT INTO kojobdnew.contacts (
  name, telephoneno, email, organization, address,
  customerid, remarks, sundry, credit, vat, created_at, updated_at
)
SELECT DISTINCT
  c.name, c.telephoneno, c.email, c.organization, c.address,
  c.customerid, c.remarks, c.sundry, c.credit, c.vat, c.created_at, c.updated_at
FROM kojobd.contacts c
JOIN kojobd.jobs j ON j.customerid = c.customerid
WHERE FIND_IN_SET(j.jid, @job_ids)
  AND c.customerid NOT IN (SELECT customerid FROM kojobdnew.contacts);

-- ===========================================================
-- STEP 2: VEHICLES
-- ===========================================================
INSERT INTO kojobdnew.vehicles (
  customerid, jobno, vregno, regdate, modelname, modelno, frameno,
  vin, color, chasisno, vcondition, daterecieved, created_at, updated_at
)
SELECT DISTINCT
  v.customerid,
  CAST(v.jobno AS UNSIGNED) + 1000 AS jobno,
  v.vregno, v.regdate, v.modelname, v.modelno, v.frameno,
  v.vin, v.color, v.chasisno, v.vcondition, v.daterecieved,
  v.created_at, v.updated_at
FROM kojobd.vehicles v
JOIN kojobd.jobs j ON j.vregno = v.vregno
WHERE FIND_IN_SET(j.jid, @job_ids)
  AND v.vregno NOT IN (SELECT vregno FROM kojobdnew.vehicles);

-- ===========================================================
-- STEP 3: JOBS
-- ===========================================================
INSERT INTO kojobdnew.jobs (
  customerid, vregno, jobno, description, dated, status,
  amount, labour, discount, sundry, vat, jid, delivered_by,
  odometer, created_at, updated_at
)
SELECT
  j.customerid, j.vregno, CAST(j.jobno AS UNSIGNED) + 1000 AS jobno,
  j.description, j.dated, j.status, j.amount, j.labour, j.discount,
  j.sundry, j.vat, j.jid, j.delivered_by, j.odometer, j.created_at, j.updated_at
FROM kojobd.jobs j
WHERE FIND_IN_SET(j.jid, @job_ids)
  AND j.jid NOT IN (SELECT jid FROM kojobdnew.jobs);

-- ===========================================================
-- STEP 4: DIAGNOSES
-- ===========================================================
INSERT INTO kojobdnew.diagnoses (
  customerid, jobno, diagnosis, problems, causes, request,
  deliverydate, status, instructions, remarks, created_at, updated_at
)
SELECT
  d.customerid, CAST(d.jobno AS UNSIGNED) + 1000 AS jobno,
  d.diagnosis, d.problems, d.causes, d.request,
  d.deliverydate, d.status, d.instructions, d.remarks,
  d.created_at, d.updated_at
FROM kojobd.diagnoses d
JOIN kojobd.jobs j ON j.jobno = d.jobno
WHERE FIND_IN_SET(j.jid, @job_ids);

-- ===========================================================
-- STEP 5: PARTS ORDERS
-- ===========================================================
INSERT INTO kojobdnew.partsorders (
  customerid, jobno, partsname, partsno, quantity, amount,
  pdate, pid, status, created_at, updated_at
)
SELECT
  p.customerid, CAST(p.jobno AS UNSIGNED) + 1000 AS jobno,
  p.partsname, p.partsno, p.quantity, p.amount,
  p.pdate, p.pid, p.status, p.created_at, p.updated_at
FROM kojobd.partsorders p
JOIN kojobd.jobs j ON j.jobno = p.jobno
WHERE FIND_IN_SET(j.jid, @job_ids);

-- ===========================================================
-- STEP 6: SERVICES ORDERS
-- ===========================================================
INSERT INTO kojobdnew.serviceorders (
  customerid, jobno, servicename, description, mileage,
  amount, sdate, nextservicedate, status, created_at, updated_at
)
SELECT
  s.customerid, CAST(s.jobno AS UNSIGNED) + 1000 AS jobno,
  s.servicename, s.description, s.mileage, s.amount,
  s.sdate, s.nextservicedate, s.status, s.created_at, s.updated_at
FROM kojobd.serviceorders s
JOIN kojobd.jobs j ON j.jobno = s.jobno
WHERE FIND_IN_SET(j.jid, @job_ids);

-- ===========================================================
-- STEP 7: SALES
-- ===========================================================
INSERT INTO kojobdnew.sales (
  customerid, jobid, salesdesc, partno, quantity, amount,
  datesold, paymethod, particulars, created_at, updated_at
)
SELECT
  sa.customerid, CAST(sa.jobid AS UNSIGNED) + 1000 AS jobid,
  sa.salesdesc, sa.partno, sa.quantity, sa.amount,
  sa.datesold, sa.paymethod, sa.particulars, sa.created_at, sa.updated_at
FROM kojobd.sales sa
JOIN kojobd.jobs j ON j.jobno = sa.jobid
WHERE FIND_IN_SET(j.jid, @job_ids);

-- ===========================================================
-- END OF MIGRATION
-- ===========================================================
SELECT 'Data migration completed successfully!' AS message;
