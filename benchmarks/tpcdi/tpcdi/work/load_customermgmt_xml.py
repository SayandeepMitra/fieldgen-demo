import duckdb
import xml.etree.ElementTree as ET

WORK = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/work")
XML_PATH = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))), "tpcdi/tpcdi-kit/staging/3/Batch1/CustomerMgmt.xml")

NS = "{http://www.tpc.org/tpc-di}"

tree = ET.parse(XML_PATH)
root = tree.getroot()
actions = root.findall(f"{NS}Action")
print(f"found {len(actions)} Action elements")

action_rows, customer_rows, name_rows, address_rows = [], [], [], []
contactinfo_rows, phone1_rows, phone2_rows, phone3_rows = [], [], [], []
taxinfo_rows, account_rows = [], []

def t(el, tag):
    child = el.find(tag)
    return child.text if child is not None and child.text is not None else None

for idx, action in enumerate(actions):
    action_id = str(idx)
    action_type = action.get("ActionType")
    action_ts = action.get("ActionTS")
    action_rows.append((action_type, action_ts, action_id))

    cust = action.find("Customer")
    if cust is None:
        continue
    customer_id = action_id  # 1:1 with Action in this schema (minOccurs=1 maxOccurs=1)

    customer_rows.append((
        cust.get("C_ID"), cust.get("C_TAX_ID"), cust.get("C_GNDR"),
        cust.get("C_TIER"), cust.get("C_DOB"), customer_id, action_id,
    ))

    name = cust.find("Name")
    if name is not None:
        name_rows.append((t(name, "C_L_NAME"), t(name, "C_F_NAME"), t(name, "C_M_NAME"), customer_id))

    addr = cust.find("Address")
    if addr is not None:
        address_rows.append((
            t(addr, "C_ADLINE1"), t(addr, "C_ADLINE2"), t(addr, "C_ZIPCODE"),
            t(addr, "C_CITY"), t(addr, "C_STATE_PROV"), t(addr, "C_CTRY"), customer_id,
        ))

    cinfo = cust.find("ContactInfo")
    if cinfo is not None:
        contactinfo_id = customer_id  # 1:1 with Customer in this schema
        contactinfo_rows.append((t(cinfo, "C_PRIM_EMAIL"), t(cinfo, "C_ALT_EMAIL"), customer_id, contactinfo_id))
        for phone_tag, bucket in [("C_PHONE_1", phone1_rows), ("C_PHONE_2", phone2_rows), ("C_PHONE_3", phone3_rows)]:
            phone = cinfo.find(phone_tag)
            if phone is not None:
                bucket.append((t(phone, "C_CTRY_CODE"), t(phone, "C_AREA_CODE"), t(phone, "C_LOCAL"), t(phone, "C_EXT"), contactinfo_id))

    taxinfo = cust.find("TaxInfo")
    if taxinfo is not None:
        taxinfo_rows.append((t(taxinfo, "C_LCL_TX_ID"), t(taxinfo, "C_NAT_TX_ID"), customer_id))

    for acct in cust.findall("Account"):
        account_rows.append((acct.get("CA_ID"), acct.get("CA_TAX_ST"), t(acct, "CA_B_ID"), t(acct, "CA_NAME"), customer_id))

TABLES = [
    ("Source.ActionXML", action_rows),
    ("Source.CustomerXML", customer_rows),
    ("Source.NameXML", name_rows),
    ("Source.AddressXML", address_rows),
    ("Source.ContactInfoXML", contactinfo_rows),
    ("Source.C_PHONE_1_XML", phone1_rows),
    ("Source.C_PHONE_2_XML", phone2_rows),
    ("Source.C_PHONE_3_XML", phone3_rows),
    ("Source.TaxInfoXML", taxinfo_rows),
    ("Source.AccountXML", account_rows),
]

con = duckdb.connect(f"{WORK}/tpcdi.duckdb")
for table, data in TABLES:
    if not data:
        print(f"{table:25s} 0 rows (skipped, no data)")
        continue
    ncols = len(data[0])
    placeholders = ", ".join(["?"] * ncols)
    con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", data)
    n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    print(f"{table:25s} {n:>10,} rows loaded")
con.close()
