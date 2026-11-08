SELECT "st_id", "st_name" FROM (SELECT TRY_CAST((CAST(st.ST_ID AS CHAR(4))) AS char(4)) AS "st_id", TRY_CAST((CAST(st.ST_NAME AS CHAR(10))) AS char(10)) AS "st_name" FROM StatusType AS st)
