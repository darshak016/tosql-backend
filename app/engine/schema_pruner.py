import re
from typing import Dict, List, Any, Set, Optional, Tuple
from collections import defaultdict

STOPWORDS = {
    "a", "an", "the", "in", "on", "of", "at", "by", "for", "with", "about",
    "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "in", "out", "over", "under",
    "again", "further", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "can", "will", "just", "should", "now",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "show", "get", "give", "me", "find", "list",
    "what", "which", "who", "whom", "this", "that", "these", "those", "am",
    "tell", "display", "query", "select", "many", "much", "per", "every"
}

def tokenize(text: str) -> Set[str]:
    """Tokenize text into lowercase alphanumeric tokens excluding common stopwords."""
    if not text:
        return set()
    raw_tokens = re.findall(r'[a-zA-Z0-9]+', text.lower())
    tokens = set()
    for t in raw_tokens:
        if t not in STOPWORDS and len(t) > 1:
            tokens.add(t)
            # Add simple singular/plural stems
            if t.endswith('ies') and len(t) > 4:
                tokens.add(t[:-3] + 'y')
            elif t.endswith('es') and len(t) > 3:
                tokens.add(t[:-2])
            elif t.endswith('s') and len(t) > 2:
                tokens.add(t[:-1])
    return tokens

class SchemaPruner:
    """
    Intelligent Schema Pruner for large relational databases:
    1. Scores tables based on lexical matching with table names, column names, sample values,
       and referenced domain glossary definitions.
    2. Computes the transitive closure of foreign keys between scored tables to ensure all
       necessary intermediate linking/join bridge tables are retained.
    3. Respects a configurable threshold and token budget.
    """
    def __init__(self, min_tables_to_prune: int = 7, default_max_tables: int = 8):
        self.min_tables_to_prune = min_tables_to_prune
        self.default_max_tables = default_max_tables

    def build_relationship_graph(self, tables: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
        """Build an undirected adjacency graph of foreign key relationships between tables."""
        adj = defaultdict(set)
        for tbl in tables:
            t_name = tbl["name"]
            for fk in tbl.get("foreign_keys", []):
                ref_tbl = fk.get("referred_table")
                if ref_tbl:
                    adj[t_name].add(ref_tbl)
                    adj[ref_tbl].add(t_name)
        return adj

    def score_tables(
        self,
        tables: List[Dict[str, Any]],
        query_tokens: Set[str],
        glossary_terms: Optional[List[Any]] = None
    ) -> Dict[str, float]:
        """
        Calculates a relevance score for each table based on:
        - Table name exact match or stem match (highest weight)
        - Column names (medium weight)
        - Sample values match (high weight for categorical filters)
        - Domain glossary matching terms (boosts associated tables)
        """
        scores: Dict[str, float] = defaultdict(float)

        # Pre-process glossary terms
        glossary_text = ""
        if glossary_terms:
            for gt in glossary_terms:
                if isinstance(gt, dict):
                    glossary_text += f" {gt.get('term', '')} {gt.get('definition', '')}"
                else:
                    glossary_text += f" {getattr(gt, 'term', '')} {getattr(gt, 'definition', '')}"
        glossary_tokens = tokenize(glossary_text)

        for tbl in tables:
            t_name = tbl["name"]
            t_tokens = tokenize(t_name)

            # 1. Match on table name
            for q_tok in query_tokens:
                if q_tok in t_tokens:
                    scores[t_name] += 12.0
                elif any(q_tok in t_tok or t_tok in q_tok for t_tok in t_tokens if len(t_tok) >= 3):
                    scores[t_name] += 6.0

            # 2. Match on columns
            for col in tbl.get("columns", []):
                col_name = col.get("name", "")
                col_tokens = tokenize(col_name)

                for q_tok in query_tokens:
                    if q_tok in col_tokens:
                        scores[t_name] += 3.5
                    elif any(q_tok in c_tok for c_tok in col_tokens if len(c_tok) >= 3):
                        scores[t_name] += 1.5

                # 3. Match on sample values
                for s_val in col.get("sample_values", []):
                    s_tokens = tokenize(str(s_val))
                    for q_tok in query_tokens:
                        if q_tok in s_tokens:
                            scores[t_name] += 4.0

            # 4. Boost if table or columns appear in active glossary definitions
            if glossary_tokens:
                if any(t_tok in glossary_tokens for t_tok in t_tokens):
                    scores[t_name] += 5.0
                for col in tbl.get("columns", []):
                    col_tokens = tokenize(col.get("name", ""))
                    if any(c_tok in glossary_tokens for c_tok in col_tokens):
                        scores[t_name] += 1.5

        return scores

    def find_bridging_tables(
        self,
        core_tables: Set[str],
        adj: Dict[str, Set[str]],
        all_tables: Dict[str, Dict[str, Any]]
    ) -> Set[str]:
        """
        Find intermediate join bridge tables between disconnected core tables using shortest path BFS.
        For instance, if 'customers' and 'products' are selected, intermediate 'orders' & 'order_items'
        bridges will be discovered and added.
        """
        if len(core_tables) <= 1:
            return set()

        bridging: Set[str] = set()
        core_list = list(core_tables)

        for i in range(len(core_list)):
            for j in range(i + 1, len(core_list)):
                start, target = core_list[i], core_list[j]
                
                # BFS to find shortest path between start and target
                visited = {start}
                queue: List[Tuple[str, List[str]]] = [(start, [start])]
                found_path: Optional[List[str]] = None

                while queue:
                    curr, path = queue.pop(0)
                    if curr == target:
                        found_path = path
                        break
                    # Max hop distance 3 to avoid pulling entire graph
                    if len(path) > 3:
                        continue
                    for neighbor in adj.get(curr, []):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append((neighbor, path + [neighbor]))

                if found_path and len(found_path) > 2:
                    for intermediate in found_path[1:-1]:
                        if intermediate in all_tables:
                            bridging.add(intermediate)

        return bridging

    def prune(
        self,
        schema: Dict[str, Any],
        user_query: str,
        previous_prompt: Optional[str] = None,
        glossary_terms: Optional[List[Any]] = None,
        max_tables: Optional[int] = None,
        force_prune: bool = False
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Performs pruning on the schema dictionary.
        Returns:
            (pruned_schema_dict, pruning_metadata)
        """
        all_tables_list = schema.get("tables", [])
        total_tables = len(all_tables_list)
        limit_tables = max_tables or self.default_max_tables

        table_dict = {tbl["name"]: tbl for tbl in all_tables_list}

        # If table count is small and force_prune is False, keep the full schema
        if total_tables <= self.min_tables_to_prune and not force_prune:
            metadata = {
                "is_pruned": False,
                "total_tables": total_tables,
                "retained_tables": [tbl["name"] for tbl in all_tables_list],
                "pruned_tables": [],
                "estimated_tokens_saved": 0
            }
            return schema, metadata

        # Collect query tokens including conversational context
        combined_text = user_query or ""
        if previous_prompt:
            combined_text += f" {previous_prompt}"

        query_tokens = tokenize(combined_text)

        # If user asks generic question with zero specific matches, retain top tables with most records/relationships
        scores = self.score_tables(all_tables_list, query_tokens, glossary_terms)

        # Sort tables by score descending
        sorted_tables = sorted(
            all_tables_list,
            key=lambda t: (scores.get(t["name"], 0), t.get("row_count", 0)),
            reverse=True
        )

        # Select primary candidate tables (tables with score > 0, up to limit_tables)
        candidate_tables: Set[str] = set()
        for t in sorted_tables:
            if scores.get(t["name"], 0) > 0 and len(candidate_tables) < limit_tables:
                candidate_tables.add(t["name"])

        # Fallback: If no tables scored > 0, pick top default core tables
        if not candidate_tables:
            fallback_count = min(limit_tables, total_tables)
            candidate_tables = {t["name"] for t in sorted_tables[:fallback_count]}

        # Build FK adjacency and expand with bridging intermediate tables
        adj = self.build_relationship_graph(all_tables_list)
        bridges = self.find_bridging_tables(candidate_tables, adj, table_dict)
        final_selected = candidate_tables.union(bridges)

        # Always preserve direct 1-hop FK neighbors if space permits under (limit_tables + 3)
        if len(final_selected) < limit_tables + 2:
            for tbl_name in list(final_selected):
                for neighbor in adj.get(tbl_name, []):
                    if neighbor in table_dict and len(final_selected) < limit_tables + 2:
                        final_selected.add(neighbor)

        # Build pruned schema
        retained_tables_list = [table_dict[name] for name in table_dict if name in final_selected]
        pruned_tables_names = [name for name in table_dict if name not in final_selected]

        # Calculate estimated token savings (rough estimate: ~25 tokens per column + ~30 per table)
        pruned_columns_count = sum(len(table_dict[p].get("columns", [])) for p in pruned_tables_names)
        estimated_tokens_saved = int(len(pruned_tables_names) * 35 + pruned_columns_count * 22)

        pruned_schema = {
            "database_type": schema.get("database_type", "sqlite"),
            "table_count": len(retained_tables_list),
            "tables": retained_tables_list
        }

        metadata = {
            "is_pruned": len(pruned_tables_names) > 0,
            "total_tables": total_tables,
            "retained_tables": [tbl["name"] for tbl in retained_tables_list],
            "pruned_tables": pruned_tables_names,
            "estimated_tokens_saved": estimated_tokens_saved if len(pruned_tables_names) > 0 else 0
        }

        return pruned_schema, metadata
