# Neo4j schema

Neo4j stores the relationship-native domain graph for papers, methods, entities,
claims, contradictions, and hypothesis seeds.

This project targets Neo4j 5 Community Edition. Do not add Enterprise-only
`NODE KEY` or property-existence constraints here; required properties are
validated by application writes.

Apply locally with:

```sh
cypher-shell -a bolt://localhost:7687 -u neo4j -p autoresearch -f schema/neo4j/constraints.cypher
cypher-shell -a bolt://localhost:7687 -u neo4j -p autoresearch -f schema/neo4j/indexes.cypher
```
