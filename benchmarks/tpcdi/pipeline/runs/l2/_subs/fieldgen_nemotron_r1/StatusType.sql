SELECT "st_id", "st_name" FROM (SELECT TRY_CAST((CAST(st.ST_ID AS TEXT)) AS TEXT) AS "st_id", TRY_CAST((CAST(st.ST_NAME AS TEXT)) AS TEXT) AS "st_name" FROM "Source"."StatusType" AS st);
