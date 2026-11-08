-- ============================================================================
-- TPC-DI v1.1.0 -- SOURCE STAGING SCHEMA  (this is your "S")
--
-- Extracted from: TPC-DI-MS-SQL-Benchmark/Helpers/Scripts/schema.sql (the "Source" half,
-- lines 1-367, preceding the "-- TPC DI Data Warehouse" marker -- see benchmark/FINDINGS.md
-- Task A2 for how this was found; CreateDBTableSchema.sql in the same repo does NOT contain
-- this schema, despite its name -- it is a second copy of T).
--
-- Converted here from SQL Server dialect to portable SQL, mirroring the conversion already
-- done for tpcdi_target_schema.sql:
--   NVARCHAR(n)  ->  VARCHAR(n)
--   DATETIME     ->  TIMESTAMP
--   trailing commas before closing parens removed
--
-- These are staging tables for the flat files TPC-DI's data generator (DIGen.jar) produces --
-- see benchmark/tpcdi/tpcdi-kit/staging/3/ for a generated instance (D) matching this schema.
-- No FK constraints in the original -- these are flat staging tables, loaded independently.
-- ============================================================================

CREATE SCHEMA Source;

CREATE TABLE Source.Account (
    CA_ID NUMERIC(11),
    CA_B_ID NUMERIC(11),
    CA_C_ID NUMERIC(11),
    CA_NAME CHAR(50),
    CA_TAX_ST NUMERIC(1),
    CA_ST_ID CHAR(4)
);

CREATE TABLE Source.BatchDate (
    BatchDate DATE
);

CREATE TABLE Source.CashTransaction (
    CT_CA_ID NUMERIC(11),
    CT_DTS TIMESTAMP,
    CT_AMT NUMERIC(10,2),
    CT_NAME CHAR(100)
);

CREATE TABLE Source.Customer (
    C_ID NUMERIC(11),
    C_TAX_ID CHAR(20),
    C_ST_ID CHAR(4),
    C_L_NAME CHAR(25),
    C_F_NAME CHAR(20),
    C_M_NAME CHAR(1),
    C_GNDR CHAR(1),
    C_TIER NUMERIC(1),
    C_DOB DATE,
    C_ADLINE1 CHAR(80),
    C_ADLINE2 CHAR(80),
    C_ZIPCODE CHAR(12),
    C_CITY CHAR(25),
    C_STATE_PROV CHAR(20),
    C_CTRY CHAR(24),
    C_CTRY_1 CHAR(3),
    C_AREA_1 CHAR(3),
    C_LOCAL_1 CHAR(10),
    C_EXT_1 CHAR(5),
    C_CTRY_2 CHAR(3),
    C_AREA_2 CHAR(3),
    C_LOCAL_2 CHAR(10),
    C_EXT_2 CHAR(5),
    C_CTRY_3 CHAR(3),
    C_AREA_3 CHAR(3),
    C_LOCAL_3 CHAR(10),
    C_EXT_3 CHAR(5),
    C_EMAIL_1 CHAR(50),
    C_EMAIL_2 CHAR(50),
    C_LCL_TX_ID CHAR(4),
    C_NAT_TX_ID CHAR(4)
);

CREATE TABLE Source.ActionXML (
    ActionType VARCHAR(9),
    ActionTS VARCHAR(256),
    Action_Id VARCHAR(256)
);

CREATE TABLE Source.CustomerXML (
    C_ID NUMERIC(11),
    C_TAX_ID VARCHAR(20),
    C_GNDR VARCHAR(1),
    C_TIER VARCHAR(256),
    C_DOB DATE,
    Customer_Id VARCHAR(256),
    Action_Id VARCHAR(256)
);

CREATE TABLE Source.NameXML (
    C_L_NAME VARCHAR(25),
    C_F_NAME VARCHAR(20),
    C_M_NAME VARCHAR(1),
    Customer_Id VARCHAR(256)
);

CREATE TABLE Source.AddressXML (
    C_ADLINE1 VARCHAR(80),
    C_ADLINE2 VARCHAR(80),
    C_ZIPCODE VARCHAR(12),
    C_CITY VARCHAR(25),
    C_STATE_PROV VARCHAR(20),
    C_CTRY VARCHAR(24),
    Customer_Id VARCHAR(256)
);

CREATE TABLE Source.ContactInfoXML (
    C_PRIM_EMAIL VARCHAR(50),
    C_ALT_EMAIL VARCHAR(50),
    Customer_Id VARCHAR(256),
    ContactInfo_Id VARCHAR(256)
);

CREATE TABLE Source.C_PHONE_1_XML (
    C_CTRY_CODE VARCHAR(3),
    C_AREA_CODE VARCHAR(3),
    C_LOCAL VARCHAR(10),
    C_EXT VARCHAR(5),
    ContactInfo_Id VARCHAR(256)
);

CREATE TABLE Source.C_PHONE_2_XML (
    C_CTRY_CODE VARCHAR(3),
    C_AREA_CODE VARCHAR(3),
    C_LOCAL VARCHAR(10),
    C_EXT VARCHAR(5),
    ContactInfo_Id VARCHAR(256)
);

CREATE TABLE Source.C_PHONE_3_XML (
    C_CTRY_CODE VARCHAR(3),
    C_AREA_CODE VARCHAR(3),
    C_LOCAL VARCHAR(10),
    C_EXT VARCHAR(5),
    ContactInfo_Id VARCHAR(256)
);

CREATE TABLE Source.TaxInfoXML (
    C_LCL_TX_ID VARCHAR(4),
    C_NAT_TX_ID VARCHAR(4),
    Customer_Id VARCHAR(256)
);

CREATE TABLE Source.AccountXML (
    CA_ID NUMERIC(11),
    CA_TAX_ST NUMERIC(1),
    CA_B_ID NUMERIC(11),
    CA_NAME VARCHAR(50),
    Customer_Id VARCHAR(256)
);

CREATE TABLE Source.DailyMarket (
    DM_DATE DATE,
    DM_S_SYMB CHAR(15),
    DM_CLOSE NUMERIC(8,2),
    DM_HIGH NUMERIC(8,2),
    DM_LOW NUMERIC(8,2),
    DM_VOL NUMERIC(12)
);

CREATE TABLE Source.Date (
    SK_DateID NUMERIC(11),
    DateValue CHAR(20),
    DateDesc CHAR(20),
    CalendarYearID NUMERIC(4),
    CalendarYearDesc CHAR(20),
    CalendarQtrID NUMERIC(5),
    CalendarQtrDesc CHAR(20),
    CalendarMonthID NUMERIC(6),
    CalendarMonthDesc CHAR(20),
    CalendarWeekID NUMERIC(6),
    CalendarWeekDesc CHAR(20),
    DayOfWeekNum NUMERIC(1),
    DayOfWeekDesc CHAR(10),
    FiscalYearID NUMERIC(4),
    FiscalYearDesc CHAR(20),
    FiscalQtrID NUMERIC(5),
    FiscalQtrDesc CHAR(20),
    HolidayFlag VARCHAR(5)
);

CREATE TABLE Source.FinwireCMP (
    PTS VARCHAR(256),
    RecType VARCHAR(256),
    CompanyName VARCHAR(256),
    CIK VARCHAR(256),
    Status VARCHAR(256),
    IndustryID VARCHAR(256),
    SPrating VARCHAR(256),
    FoundingDate VARCHAR(256),
    AddrLine1 VARCHAR(256),
    AddrLine2 VARCHAR(256),
    PostalCode VARCHAR(256),
    City VARCHAR(256),
    StateProvince VARCHAR(256),
    Country VARCHAR(256),
    CEOname VARCHAR(256),
    Description VARCHAR(256)
);

CREATE TABLE Source.FinwireSEC (
    PTS VARCHAR(256),
    RecType VARCHAR(256),
    Symbol VARCHAR(256),
    IssueType VARCHAR(256),
    Status VARCHAR(256),
    Name VARCHAR(256),
    ExID VARCHAR(256),
    ShOut VARCHAR(256),
    FirstTradeDate VARCHAR(256),
    FirstTradeExchg VARCHAR(256),
    Dividend VARCHAR(256),
    CoNameOrCIK VARCHAR(256)
);

CREATE TABLE Source.FinwireFIN (
    PTS VARCHAR(256),
    RecType VARCHAR(256),
    Year VARCHAR(256),
    Quarter VARCHAR(256),
    QtrStartDate VARCHAR(256),
    PostingDate VARCHAR(256),
    Revenue VARCHAR(256),
    Earnings VARCHAR(256),
    EPS VARCHAR(256),
    DilutedEPS VARCHAR(256),
    Margin VARCHAR(256),
    Inventory VARCHAR(256),
    Assets VARCHAR(256),
    Liabilities VARCHAR(256),
    ShOut VARCHAR(256),
    DilutedShOut VARCHAR(256),
    CoNameOrCIK VARCHAR(256)
);

CREATE TABLE Source.HoldingHistory (
    HH_H_T_ID NUMERIC(15),
    HH_T_ID NUMERIC(15),
    HH_BEFORE_QTY NUMERIC(6),
    HH_AFTER_QTY NUMERIC(6)
);

CREATE TABLE Source.HR (
    EmployeeID NUMERIC(11),
    ManagerID NUMERIC(11),
    EmployeeFirstName CHAR(30),
    EmployeeLastName CHAR(30),
    EmployeeMI CHAR(1),
    EmployeeJobCode NUMERIC(3),
    EmployeeBranch CHAR(30),
    EmployeeOffice CHAR(10),
    EmployeePhone CHAR(14)
);

CREATE TABLE Source.Industry (
    IN_ID CHAR(2),
    IN_NAME CHAR(50),
    IN_SC_ID CHAR(4)
);

CREATE TABLE Source.Prospect (
    AgencyID CHAR(30),
    LastName CHAR(30),
    FirstName CHAR(30),
    MiddleInitial CHAR(1),
    Gender CHAR(1),
    AddressLine1 CHAR(80),
    AddressLine2 CHAR(80),
    PostalCode CHAR(12),
    City CHAR(25),
    State CHAR(20),
    Country CHAR(24),
    Phone CHAR(30),
    Income NUMERIC(9),
    NumberCars NUMERIC(2),
    NumberChildren NUMERIC(2),
    MaritalStatus CHAR(1),
    Age NUMERIC(3),
    CreditRating NUMERIC(4),
    OwnOrRentFlag CHAR(1),
    Employer CHAR(30),
    NumberCreditCards NUMERIC(2),
    NetWorth NUMERIC(12)
);

CREATE TABLE Source.StatusType (
    ST_ID CHAR(4),
    ST_NAME CHAR(10)
);

CREATE TABLE Source.TaxRate (
    TX_ID CHAR(4),
    TX_NAME CHAR(50),
    TX_RATE NUMERIC(6,5)
);

CREATE TABLE Source.Time (
    SK_TimeID NUMERIC(11),
    TimeValue CHAR(20),
    HourID NUMERIC(2),
    HourDesc CHAR(20),
    MinuteID NUMERIC(2),
    MinuteDesc CHAR(20),
    SecondID NUMERIC(2),
    SecondDesc CHAR(20),
    MarketHoursFlag VARCHAR(5),
    OfficeHoursFlag VARCHAR(5)
);

CREATE TABLE Source.TradeHistory (
    TH_T_ID NUMERIC(15),
    TH_DTS TIMESTAMP,
    TH_ST_ID CHAR(4)
);

CREATE TABLE Source.Trade (
    T_ID NUMERIC(15),
    T_DTS TIMESTAMP,
    T_ST_ID CHAR(4),
    T_TT_ID CHAR(3),
    T_IS_CASH VARCHAR(5),
    T_S_SYMB CHAR(15),
    T_QTY NUMERIC(6),
    T_BID_PRICE NUMERIC(8,2),
    T_CA_ID NUMERIC(11),
    T_EXEC_NAME CHAR(49),
    T_TRADE_PRICE NUMERIC(8,2),
    T_CHRG NUMERIC(10,2),
    T_COMM NUMERIC(10,2),
    T_TAX NUMERIC(10,2)
);

CREATE TABLE Source.TradeType (
    TT_ID CHAR(3),
    TT_NAME CHAR(12),
    TT_IS_SELL NUMERIC(1),
    TT_IS_MRKT NUMERIC(1)
);

CREATE TABLE Source.WatchHistory (
    W_C_ID NUMERIC(11),
    W_S_SYMB CHAR(15),
    W_DTS TIMESTAMP,
    W_ACTION CHAR(4)
);

CREATE TABLE Source.AuditFiles (
    DataSet CHAR(20),
    BatchID NUMERIC(5),
    Date DATE,
    Attribute CHAR(50),
    Value NUMERIC(15),
    DValue NUMERIC(15,5)
);
