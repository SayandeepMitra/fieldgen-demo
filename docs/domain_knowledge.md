# Domain knowledge

Domain knowledge is what an expert knows about the move and the data model, and what the documentation does not say.
fieldgen puts it in the prompt of the recipe step, in a section called **Domain knowledge**, and next to the columns it is about.

## Where the text comes from, and how each line is labelled

Every line the tool adds says where it came from, in square brackets at the end of the line. The order of trust is: documentation first, then facts measured on your data, then expert text.

| label | meaning |
|---|---|
| `[<doc label>: <table>.<column>, guidance]` | the target documentation, word for word. The label prefix (`doc_label`) is yours, for example `OMOP documentation` |
| `[<doc label>: <table>.<column>, conventions]` | the conventions text of the documentation (shown for the target columns in the prompt) |
| `[<doc label>: <table> table description; <source> has the same columns as <table>]` | the documentation of a target table, used for a source lookup table that is a copy of it |
| `[<doc label>: <table>.<column>, domain field]` | the domain a column's concept must have (from `field_domains.json`) |
| `[Measured from the data]` | a fact the tool computed on your data (for example "18 of 22 distinct values are found in the lookup column") |
| `[Declared in the package reference tables]` | the role of each lookup table, as you listed it in `reference_tables.json` |
| `[Written by the domain expert]` | text from your `domain/` files |

You can turn the labels off (`source_labels: false`). That setting is untested.

### What the tool assembles by itself (you write none of this)

- The **target documentation** for the columns of lookup tables: when a source table has all the columns of a target table, the target's guidance is used as the description of those source columns, word for word. Expert text for the same column is dropped when documentation exists (the dropped lines are in the report).
- The **table roles**: one line per lookup table, from `reference_tables.json`.
- The **measured facts**: for a source column linked to a lookup column, how many distinct values are found there, and what the matching lookup rows look like.
- **Measured links**: a link between a source column and a lookup column when at least half (`min_coverage`) of its distinct values are found in the lookup column.
- The **conventions** of the target columns in view (`documentation_conventions`).

### What you write (all optional)

## domain_knowledge.md

General rules, in plain sentences. Template:

```text
<One sentence per rule. Say what a column or table means, in the words of an expert.>
Target columns whose name ends in _concept_id hold standard concepts. Target columns whose name
ends in _source_concept_id hold the concept of the code as written in the source data.
```

## flow_text.md

How a code or value in a source table becomes a value in the target. A short numbered list works best. Our example for the OMOP move:

```text
How a code in a source table becomes a target concept:
1. Find the concept_seed row whose concept_code equals the code and whose vocabulary_id is the
   coding system of that source column. Its concept_id is the source concept.
2. Find the concept_relationship_seed row with concept_id_1 = that concept_id, relationship_id
   'Maps to' and invalid_reason NULL. Its concept_id_2 is the standard concept. A standard concept
   maps to itself.
3. The concept_seed row of concept_id_2 has standard_concept 'S' and a domain_id.
4. A source record belongs in the target table whose concept column accepts that domain. The *_concept_id
   column takes the standard concept, the *_source_concept_id column the source concept, the
   *_source_value column the code.

The domain of the standard concept (concept_id_2) decides the target table. The source concept may belong
to a different domain; its domain does not decide the table.
```

Write it for your move: name the tables and columns, say which one decides what. The tool puts each numbered step on its own line and labels it.
Every value in quotes should exist in your data with the same spelling (the data check warns if not).

## descriptions_supplement.json

Descriptions for source tables and columns that have none in the documentation. `column: null` describes the table.

```json
[{"table": "state_codes", "column": null, "text": "Codes of the states an order is shipped to.", "provenance": "supplied by project expert"},
 {"table": "state_codes", "column": "code", "text": "Two letter code of the state.", "provenance": "supplied by project expert"}]
```

When the target documentation has text for the same column of a lookup copy, the documentation wins.

## value_meanings.json

What a coded value means, for source columns.

```json
[{"table": "customers", "column": "status_code", "value": "A", "meaning": "Active customer."}]
```

Also dropped when the documentation already describes the column.

## domain_text.json

Labels and one setting for the documentation lines. Example for OMOP:

```json
{"doc_label": "OMOP documentation",
 "rule_table": "domain",
 "rule_label": "OMOP documentation: domain table description",
 "empty_markers": ["", "NA"]}
```

- `doc_label`: the name that starts the documentation labels.
- `rule_table` (optional): a target table whose description is a general rule worth showing once in every prompt (OMOP: the `domain` table).
- `empty_markers`: texts that mean "no documentation" in your documentation files.

## Tips

- Keep each line short and checkable. A rule that is wrong costs more than a missing rule.
- Say what is true of the data. Do not tell the model how to write SQL.
- Do not copy the reference conversion into the text. `fieldgen test` looks for it and stops if reference text is found in the package.
- After a change, run `fieldgen check` and read the "text data check" lines in `report.md`: quoted values that are not in your data are listed there.
