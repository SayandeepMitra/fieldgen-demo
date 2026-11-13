# Builds the two fieldgen input packages used in the experiments (run 6: customer tables as XML events; run 10: one CustomerHistory table),
# each as WORK/packages/<run>/package + WORK/packages/<run>/reference. Uses `fieldgen init`, then fills what init leaves open.
# The specification text is read from --spec at run time (column descriptions and rules, each tagged with its clause number); nothing of it is stored in this folder.
# Usage: python make_package.py --work WORK --spec spec_pages.txt   (needs build_source.py, build_gold.py, build_history.py done first)
import sys, os, re, csv, json, shutil, argparse, collections
from pathlib import Path
import duckdb

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--work", required=True, help="work folder: holds source/ (build_source.py), gold/ (build_gold.py), source_hist.duckdb (build_history.py); packages/ is written here")
ap.add_argument("--spec", required=True, help="text of the TPC-DI specification (one text file, as extracted from the PDF); read only, never copied")
ap.add_argument("--column-map", default=str(HERE / "column_map.csv"), help="table.column -> source columns (no specification text)")
ap.add_argument("--expert-text", default=str(HERE / "expert_text"), help="folder with run6/run10 flow_text.md and config.yaml")
ap.add_argument("--fieldgen", default=None, help="folder that holds the fieldgen package (default: the project folder two levels up)")
a = ap.parse_args()
WORK = Path(a.work).resolve()
for cand in [a.fieldgen, HERE.parents[1], HERE.parents[1] / "src"]:
    if cand and (Path(cand) / "fieldgen" / "__init__.py").exists(): sys.path.insert(0, str(cand)); break
from fieldgen.init_package import init_package

TABLES = ["dimdate", "dimtime", "statustype", "taxrate", "tradetype", "industry", "dimbroker", "dimcompany", "dimcustomer"]
KEY = {"dimdate": "sk_dateid", "dimtime": "sk_timeid", "statustype": "st_id", "taxrate": "tx_id", "tradetype": "tt_id", "industry": "in_id",
       "dimbroker": "brokerid", "dimcompany": "companyid", "dimcustomer": "customerid"}
CSV_NAME = {"dimdate": "DimDate", "dimtime": "DimTime", "statustype": "StatusType", "taxrate": "TaxRate", "tradetype": "TradeType",
            "industry": "Industry", "dimbroker": "DimBroker", "dimcompany": "DimCompany", "dimcustomer": "DimCustomer"}
REN = {"Action_Id": "ActionSeq", "Customer_Id": "CustomerSeq", "ContactInfo_Id": "ContactSeq"}   # link columns renamed so they do not look like keys
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
rj = lambda p: json.load(open(p, encoding="utf-8"))
def wj(p, o): json.dump(o, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def write_field_docs(spec_path, pkg):
    """Reads the specification text (from spec_path, at run time) and writes pkg/target/field_docs.json:
    column descriptions (section 3.2.x) as guidance, transformation rules (4.5.x) as conventions, each line ending with its clause number."""
    PKG = Path(pkg)
    SPEC = Path(spec_path).read_text(encoding="utf-8").split("\n")
    LABEL = "TPC-DI documentation"
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    def is_noise(l): return l.startswith("=====PAGE") or l.startswith("TPC Benchmark") or not l.strip()
    def find(heading, start=1350):
        for i in range(start, len(SPEC)):
            if SPEC[i].strip() == heading or SPEC[i].startswith(heading + " ") and "...." not in SPEC[i]: return i
        raise KeyError(heading)
    T = {  # target table -> (section 3 heading, section 4.5 heading)
     "dimbroker": ("3.2.2 DimBroker", "4.5.2 DimBroker"), "dimcompany": ("3.2.3 DimCompany", "4.5.3 DimCompany"),
     "dimcustomer": ("3.2.4 DimCustomer", "4.5.4 DimCustomer"), "dimdate": ("3.2.5 DimDate", "4.5.5 DimDate"),
     "dimtime": ("3.2.7 DimTime", "4.5.7 DimTime"), "industry": ("3.2.13 Industry", "4.5.13 Industry"),
     "statustype": ("3.2.16 StatusType", "4.5.16 StatusType"), "taxrate": ("3.2.17 TaxRate", "4.5.17 TaxRate"),
     "tradetype": ("3.2.18 TradeType", "4.5.18 TradeType")}
    tables = json.load(open(PKG / "target/tables.json", encoding="utf-8"))

    tcols = {t["name"]: [c["name"] for c in t["columns"]] for t in tables}
    def section_end(i, pat):
        j = i + 1
        while j < len(SPEC) and not re.match(pat, SPEC[j]): j += 1
        return j
    FIELD = re.compile(r"^([A-Za-z][A-Za-z0-9_]*) (?:SK_T|IDENT_T|[A-Z_]+\(\d+(?:,\d+)?\)|[A-Z_]+) (?:Not NULL )?(.*)$")
    def section3(table):
        h3 = T[table][0]; i = find(h3); j = section_end(i, r"^3\.2\.\d+(\.\d+)? [A-Za-z]")
        allnames = {norm(n) for n in tcols[table]} | {"dayofweeknum"} | {norm(x) for x in ["SK_BrokerID","IsCurrent","BatchID","EffectiveDate","EndDate","SK_CompanyID","SK_CustomerID"]}
        desc = {}; cur = None
        for l in SPEC[i + 1:j]:
            if is_noise(l) or l.startswith("Table 3.2") or l.startswith("Field Name"): continue
            m = FIELD.match(l)
            if m and norm(m.group(1)) in allnames: cur = norm(m.group(1)); desc[cur] = [m.group(2)]
            elif cur: desc[cur].append(l.strip())
        return h3.split()[0], {k: " ".join(v) for k, v in desc.items()}
    def clauses(table):
        """4.5.x clause paragraphs: [(clause number, text)] before the first bullet-list clause marker."""
        h = T[table][1]; i = find(h, 2200); j = section_end(i, r"^4\.5\.\d+ [A-Za-z]|^4\.6 ")
        out = []; cur = None
        for l in SPEC[i + 1:j]:
            if l.startswith("=====PAGE") or l.startswith("TPC Benchmark"): continue
            m = re.match(r"^(4\.5\.\d+\.\d+) (.*)$", l)
            if m and m.group(1).startswith(h.split()[0] + "."): cur = [m.group(1), [m.group(2)]]; out.append(cur)
            elif cur is not None: cur[1].append(l.rstrip())
        return [(c, [x for x in ls]) for c, ls in out]
    def bullets(lines, allcols):
        """Split lines into top-level bullets ('x ' glyph). Nested bullets are merged into the previous top-level bullet."""
        chunks = []
        for l in lines:
            if l.startswith("x "):
                chunks.append([l[2:].rstrip()])
            elif chunks: chunks[-1].append(l.rstrip())
            else: chunks.append(["" + l.rstrip()])
        TOP = re.compile(r"^(When |Fields |A history|All current|Records where)")
        top = []
        for ch in chunks:
            first = ch[0]; w = norm(re.split(r"[ ,:]", first, 1)[0])
            if TOP.match(first) or w in allcols or not top: top.append(ch)
            else: top[-1].extend(ch)
        return top
    def head_cols(text, allcols):
        toks = re.findall(r"[A-Za-z0-9_/.@']+|[,:]", text[:300]); out = []
        for tk in toks:
            n = norm(tk)
            if tk in (",", ":") or n == "and": continue
            if n in allcols: out.append(n)
            else: break
        return out
    join = lambda ls: " ".join(s.strip() for s in ls if s.strip())
    ALIAS = {"dayofweeknumeric": "dayofweeknum"}  # repo DDL name -> spec field name
    docs = {"tables": {}, "fields": {}}
    count = collections.Counter(); excluded = []
    old_docs = json.load(open(PKG / "target/field_docs.json", encoding="utf-8"))
    for table, (h3, h45) in T.items():
        clause3, d3 = section3(table); cl = clauses(table)
        allc = set(norm(c) for c in tcols[table]) | {norm(x) for x in ["SK_BrokerID","SK_CompanyID","SK_CustomerID","IsCurrent","BatchID","EffectiveDate","EndDate","State_Prov"]}
        allc.add("stateprov"); allc.add("stateprov")
        tlevel = []; percol = collections.defaultdict(list)
        for num, ls in cl:
            # clauses that are a bullet list are split; others are a table-level paragraph
            if any(l.startswith("x ") for l in ls) or num in ("4.5.4.3",):
                intro = []; rest = ls
                k = next((n for n, l in enumerate(ls) if l.startswith("x ")), len(ls))
                intro = ls[:k]; rest = ls[k:]
                if intro and join(intro): tlevel.append((num, join(intro)))
                if table == "dimcustomer" and num == "4.5.4.3":
                    parts = []; cur_ = None
                    for l in rest:
                        mm = re.match(r"^x When \./@ActionType is .(NEW|UPDCUST|INACT).", l)
                        if mm: cur_ = [mm.group(1), []]; parts.append(cur_)
                        elif cur_ is not None: cur_[1].append(l)
                    groups = [(f"{num}, {a}", ls_) for a, ls_ in parts]
                else: groups = [(num, rest)]
                for lab, gl in groups:
                    for ch in bullets(gl, allc):
                        txt = join(ch); hc = head_cols(txt, allc)
                        if re.search(r"DimAccount|accounts", txt) and not hc: excluded.append((table, lab, txt[:80])); continue
                        entry = f"{txt} [{LABEL}: clause {lab}]"
                        if not hc:
                            if not re.match(r"^(IsCurrent|SK_|BatchID|EffectiveDate)", txt): tlevel.append((lab, txt))
                            continue
                        hc = ["stateprov" if c == "stateprov" else c for c in hc]
                        for c in hc:
                            if c in {norm(x) for x in tcols[table]}: percol[c].append(entry)
            else:
                body = join(ls)
                if num == "4.5.3.3" and table == "dimcompany":
                    for c in ("sprating", "islowgrade"): percol[c].append(f"{body} [{LABEL}: clause {num}]")
                elif re.search(r"with no modifications", body):
                    for c in tcols[table]: percol[norm(c)].append(f"{body} [{LABEL}: clause {num}]")
                    tlevel.append((num, body))
                elif "DImessages" in body: excluded.append((table, num, body[:80]))   # message-table rules: no such target table
                else: tlevel.append((num, body))
        tl = []; seen = set()
        for num, txt in tlevel:
            e = f"{txt} [{LABEL}: clause {num}]"
            if e not in seen: seen.add(e); tl.append(e)
        docs["tables"][table] = {"description": None, "guidance": "\n".join(tl) or None, "conventions": None}
        count[table] += len(tl)
        for c in tcols[table]:
            g = f"{d3[ALIAS.get(norm(c), norm(c))]} [{LABEL}: clause {clause3}]"
            conv = percol.get(norm(c), [])
            docs["fields"][f"{table}.{c}"] = {"guidance": g, "conventions": "\n".join(conv) or None,
                "ddl": old_docs["fields"][f"{table}.{c}"]["ddl"]}
            count[table] += 1 + len(conv)
    json.dump(docs, open(PKG / "target/field_docs.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return docs


def main_schema_copy(src_db, out_db):
    """init reads only schema main: copy the Source tables there, link columns renamed."""
    if os.path.exists(out_db): os.remove(out_db)
    con = duckdb.connect(out_db); con.execute(f"ATTACH '{src_db}' AS s (READ_ONLY)")
    for (t,) in con.execute("select table_name from information_schema.tables where table_catalog='s' and table_schema='Source' order by 1").fetchall():
        cols = [r[0] for r in con.execute(f"select column_name from information_schema.columns where table_catalog='s' and table_schema='Source' and table_name='{t}' order by ordinal_position").fetchall()]
        con.execute(f"CREATE TABLE main.{t} AS SELECT " + ", ".join(f'"{c}" AS "{REN.get(c, c)}"' for c in cols) + f" FROM s.Source.{t}")
    con.close()


def fix_links(pkg, history):
    """Drop the weak 'value_only' links init proposes (coincidences of values); the two company lookups are stated by the documentation, so keep them."""
    links = rj(pkg / "source/links.json"); out = []
    for k in links:
        if k["support"] == "value_only":
            if k["child"] == "FinwireCMP" and k["parent"] in ("StatusType", "Industry"):
                k.update(provenance="declared", support="dictionary", weak=False, note="join stated by the target documentation" + ("" if history else " (company status and industry are looked up by code)"))
                out.append(k)
        else: out.append(k)
    wj(pkg / "source/links.json", out)


def set_keys(pkg, table, pk, business_ids, note):
    tabs = rj(pkg / "source/tables.json")
    for t in tabs:
        if t["name"] == table: t["pk"] = pk; t["business_ids"] = business_ids; t["pk_provenance"] = {"source": "set by hand", "note": note} if note else t["pk_provenance"]
    wj(pkg / "source/tables.json", tabs)


def target_keys_and_label(pkg):
    """Target primary keys = the business key of each table (the DDL has UNIQUE only); documentation label for the prompts."""
    tt = rj(pkg / "target/tables.json")
    for t in tt: t["pk"] = [KEY[t["name"]]]
    wj(pkg / "target/tables.json", tt)
    dt = rj(pkg / "domain/domain_text.json"); dt["doc_label"] = "TPC-DI documentation"; wj(pkg / "domain/domain_text.json", dt)


def only_dimcustomer(pkg, name):
    """These two experiments build only DimCustomer: keep its target table, documentation and matches."""
    tt = [t for t in rj(pkg / "target/tables.json") if t["name"] == "dimcustomer"]; wj(pkg / "target/tables.json", tt)
    fd = rj(pkg / "target/field_docs.json")
    fd["tables"] = {k: v for k, v in fd["tables"].items() if k == "dimcustomer"}
    fd["fields"] = {k: v for k, v in fd["fields"].items() if k.startswith("dimcustomer.")}; wj(pkg / "target/field_docs.json", fd)
    m = rj(pkg / "matches/matches.json"); wj(pkg / "matches/matches.json", {k: v for k, v in m.items() if k.startswith("dimcustomer.")})
    mf = rj(pkg / "manifest.json"); mf["name"] = name; mf["target_tables"] = 1; wj(pkg / "manifest.json", mf)   # names as in the recorded runs


def write_matches(pkg, db, mapcol=lambda tab, col: (tab, col)):
    """Matches = the source columns named in column_map.csv ('source tables.columns' only, no rule text), mapped to the tables of this package."""
    con = duckdb.connect(str(db), read_only=True); have = {}
    for t, c in con.execute("select table_name, column_name from information_schema.columns where table_schema='main'").fetchall(): have.setdefault(t, set()).add(c)
    m = rj(pkg / "matches/matches.json"); new = {k: [] for k in m}; missing = []
    for r in csv.DictReader(open(a.column_map, encoding="utf-8")):
        key = f'{r["table"]}.{r["column"]}'.lower()
        if key not in new: continue
        for seg in [s.strip() for s in r["source tables.columns"].split(";") if s.strip()]:
            tab = None
            for tk in [t.strip() for t in seg.split(",") if t.strip()]:
                if tk.startswith("Source."): _, tab, col = tk.split(".", 2)
                else: col = tk
                if tab is None: missing.append(f"{key}: no table for {tk}"); continue
                rel, c = mapcol(tab, col)
                if c not in have.get(rel, set()): missing.append(f"{key}: {rel}.{c} not in the source"); continue
                e = {"relation": rel, "column": c}
                if e not in new[key]: new[key].append(e)
    wj(pkg / "matches/matches.json", new)
    con.close()
    return sum(1 for v in new.values() if v), len(new), missing


def history_column(tab, col):
    """Customer tables of the XML source -> columns of CustomerHistory."""
    if tab in {"CustomerXML", "ActionXML", "NameXML", "AddressXML", "ContactInfoXML", "TaxInfoXML"}: return "CustomerHistory", col
    if tab.startswith("C_PHONE_") and tab.endswith("_XML"): return "CustomerHistory", f"{col}_{tab.split('_')[2]}"
    return tab, col


def write_reference(ref, only_customer, history):
    """reference/: gold tables with lower-case headers + alignment.json (which source column identifies a row)."""
    (ref / "reference_data").mkdir(parents=True, exist_ok=True)
    for t in (["dimcustomer"] if only_customer else TABLES):
        rows = list(csv.reader(open(WORK / "gold/gold_csv" / f"{CSV_NAME[t]}.csv", encoding="utf-8")))
        rows[0] = [h.lower() for h in rows[0]]
        csv.writer(open(ref / "reference_data" / f"{t}.csv", "w", newline="", encoding="utf-8")).writerows(rows)
    align = {"dimdate": "Date.SK_DateID", "dimtime": "Time.SK_TimeID", "statustype": "StatusType.ST_ID", "taxrate": "TaxRate.TX_ID", "tradetype": "TradeType.TT_ID",
             "industry": "Industry.IN_ID", "dimbroker": "HR.EmployeeID", "dimcompany": "FinwireCMP.CIK", "dimcustomer": "CustomerXML.C_ID"}
    if history: align = {"dimcustomer": "CustomerHistory.C_ID"}
    wj(ref / "alignment.json", {t: {"source": [s], "reference": [KEY[t]], "exclude": []} for t, s in align.items()})


def add_expert_files(pkg, run):
    d = Path(a.expert_text)
    shutil.copy(d / f"{run}_config.yaml", pkg / "config.yaml")
    (pkg / "domain").mkdir(exist_ok=True); shutil.copy(d / f"{run}_flow_text.md", pkg / "domain/flow_text.md")
    for f in ("domain_knowledge.md", ):
        if (pkg / "domain" / f).exists(): (pkg / "domain" / f).unlink()
    if (pkg / "TODO.md").exists(): (pkg / "TODO.md").unlink()


def build(run, source_db, target_ddl, history):
    pkg = WORK / "packages" / run / "package"; ref = WORK / "packages" / run / "reference"
    for p in (pkg.parent,):
        if p.exists(): shutil.rmtree(p)
    init_package(str(pkg), str(source_db), str(target_ddl))
    fix_links(pkg, history); target_keys_and_label(pkg)
    if history:
        set_keys(pkg, "CustomerHistory", ["ActionSeq"], ["C_ID"], "one row per action; ActionSeq unique")
    else:
        set_keys(pkg, "ActionXML", ["ActionSeq"], ["ActionSeq"], None)
        links = rj(pkg / "source/links.json")      # init stops proposing this link once ActionXML has this key: add it by hand
        links.append({"child": "CustomerXML", "child_columns": ["ActionSeq"], "parent": "ActionXML", "parent_columns": ["ActionSeq"], "cardinality": "one_to_one",
                      "provenance": "supplemented", "support": "name", "weak": False, "coverage": 1.0,
                      "note": "restored by hand: init no longer proposed it after ActionXML got a different proposed key"})
        wj(pkg / "source/links.json", links)
    write_field_docs(a.spec, pkg)
    only_dimcustomer(pkg, "package_tpcdi_exp8" if history else "package_tpcdi_exp3")
    nm, nk, missing = write_matches(pkg, source_db, history_column if history else (lambda tab, col: (tab, col)))
    add_expert_files(pkg, run)
    write_reference(ref, only_customer=history, history=history)
    print(f"{run}: package {pkg} | matches {nm} of {nk} columns | missing names {len(missing)}")
    for x in missing: print("  MISSING", x)


tmp = WORK / "tmp"; tmp.mkdir(parents=True, exist_ok=True)
xml_main = tmp / "source_xml_main.duckdb"
main_schema_copy(str(WORK / "source/tpcdi_source.duckdb"), str(xml_main))
build("run6", xml_main, WORK / "source/target_ddl.sql", history=False)
build("run10", WORK / "source_hist.duckdb", WORK / "source/target_ddl.sql", history=True)
shutil.rmtree(tmp)
print("done: WORK/packages/run6 and WORK/packages/run10 (each with package/ and reference/)")
