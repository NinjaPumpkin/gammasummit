# data/

Local development data only. **Gitignored entirely** (except this README).

- Local dev databases, Parquet samples, downloaded fixtures live here.
- Never production data dumps in git — export artifacts go to cold storage
  (external disk / B2/R2), not here.
- Anything in this folder is disposable and must never be a system of record.
