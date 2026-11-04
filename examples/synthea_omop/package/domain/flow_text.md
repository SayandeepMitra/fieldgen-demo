How a code in a source table becomes a target concept:
1. Find the concept_seed row whose concept_code equals the code and whose vocabulary_id is the coding
   system of that source column. Its concept_id is the source concept.
2. Find the concept_relationship_seed row with concept_id_1 = that concept_id, relationship_id 'Maps to'
   and invalid_reason NULL. Its concept_id_2 is the standard concept. A standard concept maps to itself.
3. The concept_seed row of concept_id_2 has standard_concept 'S' and a domain_id.
4. A source record belongs in the target table whose concept column accepts that domain. The *_concept_id
   column takes the standard concept, the *_source_concept_id column the source concept, the
   *_source_value column the code.

The domain of the standard concept (concept_id_2) decides the target table. The source concept may belong to a different domain; its domain does not decide the table.
