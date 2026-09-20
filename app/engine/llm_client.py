import os
import json
import re
from typing import Dict, Any, Optional
from app.core.config import settings
from app.engine.prompt_builder import SYSTEM_INSTRUCTION

class LLMClient:
    def __init__(self, api_key: Optional[str] = None, provider: str = "gemini", model_name: Optional[str] = None):
        self.provider = provider.lower()
        self.api_key = api_key or (settings.GEMINI_API_KEY if self.provider == "gemini" else settings.OPENAI_API_KEY)
        self.model_name = model_name or (settings.DEFAULT_MODEL if self.provider == "gemini" else "gpt-4o-mini")

    def generate_sql(
        self, 
        prompt: str, 
        user_query: str = "", 
        previous_sql: Optional[str] = None,
        glossary_terms: Optional[list] = None,
        few_shot_examples: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Sends prompt to configured LLM (Gemini / OpenAI) or falls back to intelligent mock generator.
        """
        # Try Gemini if API key is provided
        if self.provider == "gemini" and self.api_key:
            return self._call_gemini(prompt)

        # Try OpenAI if API key is provided
        if self.provider == "openai" and self.api_key:
            return self._call_openai(prompt)

        # If system environment has GEMINI_API_KEY
        env_gemini_key = os.environ.get("GEMINI_API_KEY")
        if env_gemini_key:
            self.api_key = env_gemini_key
            self.provider = "gemini"
            return self._call_gemini(prompt)

        # If system environment has OPENAI_API_KEY
        env_openai_key = os.environ.get("OPENAI_API_KEY")
        if env_openai_key:
            self.api_key = env_openai_key
            self.provider = "openai"
            return self._call_openai(prompt)

        # Fallback to local intelligent mock engine for demo database
        return self._fallback_demo_generator(
            user_query or prompt, 
            prompt=prompt, 
            previous_sql=previous_sql,
            glossary_terms=glossary_terms,
            few_shot_examples=few_shot_examples
        )


    def _call_gemini(self, prompt: str) -> Dict[str, Any]:
        try:
            # Try official google.genai first
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name or "gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json"
                )
            )
            raw_text = response.text
            return self._clean_and_parse_json(raw_text)
        except Exception as genai_err:
            # Fallback to google.generativeai if available
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=self.api_key)
                model = legacy_genai.GenerativeModel(
                    model_name="gemini-1.5-flash",
                    system_instruction=SYSTEM_INSTRUCTION
                )
                response = model.generate_content(prompt)
                return self._clean_and_parse_json(response.text)
            except Exception as legacy_err:
                raise RuntimeError(f"Gemini API Error: {str(genai_err)} | Fallback Error: {str(legacy_err)}")

    def _call_openai(self, prompt: str) -> Dict[str, Any]:
        from openai import OpenAI
        client = OpenAI(
            api_key=self.api_key,
            base_url=settings.OPENAI_BASE_URL or None
        )
        response = client.chat.completions.create(
            model=self.model_name or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        raw_text = response.choices[0].message.content
        return self._clean_and_parse_json(raw_text)

    def _clean_and_parse_json(self, raw_text: str) -> Dict[str, Any]:
        cleaned = raw_text.strip()
        # Remove ```json ... ``` wrappers if present
        cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        
        try:
            data = json.loads(cleaned)
            return data
        except json.JSONDecodeError:
            # Try regex extraction of JSON block
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise ValueError(f"Could not parse LLM output into JSON. Raw output: {raw_text[:200]}")

    def _fallback_demo_generator(
        self, 
        user_query: str, 
        prompt: str = "", 
        previous_sql: Optional[str] = None,
        glossary_terms: Optional[list] = None,
        few_shot_examples: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Intelligent offline heuristic generator for bundled sample queries if no API key is set yet.
        Enables testing and UI previewing out-of-the-box while properly handling greetings, follow-ups, few-shots, and glossary rules!
        """
        # If full prompt was passed, extract the raw user question
        if "### Current User Request:" in prompt:
            match = re.search(r'### Current User Request:\s*"?(.*?)"?\s*(?:\n###|\nGenerate|$)', prompt, re.DOTALL)
            if match:
                user_query = match.group(1).strip()
        elif "### User Question:" in prompt:
            match = re.search(r'### User Question:\s*"?(.*?)"?\s*(?:\n###|\nGenerate|$)', prompt, re.DOTALL)
            if match:
                user_query = match.group(1).strip()

        # Clean string for semantic checking
        clean_q = re.sub(r"[-_]", " ", user_query.lower())
        clean_q = re.sub(r"[^\w\s]", " ", clean_q)
        clean_q = re.sub(r"\s+", " ", clean_q).strip()

        # 0. Check custom few-shot examples registered by user/admin
        if few_shot_examples:
            for ex in few_shot_examples:
                ex_prompt = (ex.get("prompt") if isinstance(ex, dict) else getattr(ex, "prompt", "")) or ""
                clean_ex = re.sub(r"[^\w\s]", " ", ex_prompt.lower()).strip()
                if clean_ex and (clean_ex == clean_q or clean_ex in clean_q or clean_q in clean_ex):
                    ex_sql = (ex.get("sql") if isinstance(ex, dict) else getattr(ex, "sql", "")) or ""
                    ex_expl = (ex.get("explanation") if isinstance(ex, dict) else getattr(ex, "explanation", "")) or "Generated from matching registered few-shot reference example."
                    return {
                        "sql": ex_sql,
                        "explanation": ex_expl,
                        "suggested_chart": "table",
                        "chart_config": {}
                    }

        # 1. Handle Greetings & Conversational Inputs (only if not a follow-up refinement)
        greetings = {
            "hello", "hi", "hey", "hola", "greetings", "good morning", 
            "good afternoon", "good evening", "howdy", "sup", "yo",
            "how are you", "who are you", "what can you do", "help", "test"
        }
        if (clean_q in greetings or len(clean_q) <= 2) and not previous_sql:
            return {
                "sql": "",
                "explanation": "Hello! I am your AI Text-to-SQL Assistant. Ask me a question about your database (for example: 'Show top 5 customers by spend', 'Monthly revenue trend', or 'Which products are low on stock?').",
                "suggested_chart": "table",
                "chart_config": {}
            }


        # 2. Conversational Follow-up Refinements (Phase 2.1)
        if previous_sql:
            mod_sql = previous_sql.strip().rstrip(';')

            # Check for limit refinement (e.g. "top 10", "limit 3", "only 5")
            limit_match = re.search(r'\b(?:top|limit|only|first)\s+(\d+)\b', clean_q)
            if limit_match:
                new_limit = limit_match.group(1)
                if re.search(r'\bLIMIT\s+\d+\b', mod_sql, re.IGNORECASE):
                    mod_sql = re.sub(r'\bLIMIT\s+\d+\b', f'LIMIT {new_limit}', mod_sql, flags=re.IGNORECASE)
                else:
                    mod_sql = f"{mod_sql}\nLIMIT {new_limit}"
                return {
                    "sql": mod_sql,
                    "explanation": f"Refined the previous query to limit results to {new_limit} records based on your follow-up.",
                    "suggested_chart": "table",
                    "chart_config": {}
                }

            # Check for sorting direction (e.g. "order by asc", "lowest first", "descending")
            if any(term in clean_q for term in ["ascending", "asc", "lowest first", "cheapest first"]):
                if re.search(r'\bDESC\b', mod_sql, re.IGNORECASE):
                    mod_sql = re.sub(r'\bDESC\b', 'ASC', mod_sql, flags=re.IGNORECASE)
                    return {
                        "sql": mod_sql,
                        "explanation": "Updated sort order to ascending (lowest/cheapest first) according to your follow-up instruction.",
                        "suggested_chart": "table",
                        "chart_config": {}
                    }

            # Check for country/status filter additions
            if "usa" in clean_q or "united states" in clean_q:
                condition = "country = 'USA'" if "country" not in mod_sql else "c.country = 'USA'"
                if "WHERE" in mod_sql.upper():
                    mod_sql = re.sub(r'(\bWHERE\b\s+)(.*?)(\bGROUP\b|\bORDER\b|\bLIMIT\b|$)', rf'\1\2 AND {condition} \3', mod_sql, flags=re.IGNORECASE | re.DOTALL)
                else:
                    mod_sql = re.sub(r'(\bFROM\b.*?)(\bGROUP\b|\bORDER\b|\bLIMIT\b|$)', rf'\1 WHERE {condition} \2', mod_sql, flags=re.IGNORECASE | re.DOTALL)
                return {
                    "sql": mod_sql.strip(),
                    "explanation": "Refined previous query to only include customers/records from the USA.",
                    "suggested_chart": "table",
                    "chart_config": {}
                }

        # 3. Check for Specific Analytical Query Intents
        is_postgres = ("postgresql" in prompt.lower()) or ("first_name" in prompt)

        if any(term in clean_q for term in ["campaign", "marketing", "ad spend", "roi"]):
            return {
                "sql": """SELECT campaign_name, channel, budget, actual_spend, revenue_generated, roi_percentage
FROM marketing_campaigns
ORDER BY revenue_generated DESC
LIMIT 5""",
                "explanation": "Retrieves the top 5 marketing campaigns ranked by generated revenue, including channel, budget, spend, and ROI percentage.",
                "suggested_chart": "bar",
                "chart_config": {
                    "x_axis": "campaign_name",
                    "y_axis": "revenue_generated",
                    "title": "Top Marketing Campaigns by Revenue ($)"
                }
            }

        elif any(term in clean_q for term in ["department", "employee", "salary", "payroll", "headcount", "staff"]):
            return {
                "sql": """SELECT d.name AS department_name, d.manager_name, COUNT(e.id) AS employee_count, ROUND(AVG(e.salary), 2) AS avg_salary, d.annual_budget
FROM departments d
LEFT JOIN employees e ON d.id = e.department_id
GROUP BY d.id, d.name, d.manager_name, d.annual_budget
ORDER BY employee_count DESC""",
                "explanation": "Calculates the employee headcount, average salary, and budget for each organizational department.",
                "suggested_chart": "bar",
                "chart_config": {
                    "x_axis": "department_name",
                    "y_axis": "avg_salary",
                    "title": "Average Employee Salary by Department ($)"
                }
            }

        elif any(term in clean_q for term in ["subscription", "mrr", "plan", "saas", "recurring"]):
            return {
                "sql": """SELECT p.plan_name, p.billing_interval, p.price, COUNT(s.id) AS subscriber_count, ROUND(SUM(s.mrr_value), 2) AS total_mrr
FROM subscription_plans p
LEFT JOIN customer_subscriptions s ON p.id = s.plan_id
GROUP BY p.id, p.plan_name, p.billing_interval, p.price
ORDER BY total_mrr DESC""",
                "explanation": "Aggregates Monthly Recurring Revenue (MRR) and active subscriber counts grouped by subscription tier.",
                "suggested_chart": "bar",
                "chart_config": {
                    "x_axis": "plan_name",
                    "y_axis": "total_mrr",
                    "title": "Monthly Recurring Revenue (MRR) by Plan ($)"
                }
            }

        elif any(term in clean_q for term in ["ticket", "support", "csat", "nps", "satisfaction"]):
            return {
                "sql": """SELECT category, priority, status, COUNT(id) AS ticket_count
FROM support_tickets
GROUP BY category, priority, status
ORDER BY ticket_count DESC
LIMIT 10""",
                "explanation": "Aggregates customer support tickets by category, priority, and resolution status.",
                "suggested_chart": "pie",
                "chart_config": {
                    "x_axis": "category",
                    "y_axis": "ticket_count",
                    "title": "Support Tickets Distribution by Category"
                }
            }

        elif any(term in clean_q for term in ["warehouse", "inventory location", "stored", "stock by warehouse"]):
            return {
                "sql": """SELECT w.name AS warehouse_name, w.city, w.country, COUNT(wi.product_id) AS stored_products, SUM(wi.quantity_on_hand) AS total_units_stored
FROM warehouses w
LEFT JOIN warehouse_inventory wi ON w.id = wi.warehouse_id
GROUP BY w.id, w.name, w.city, w.country
ORDER BY total_units_stored DESC""",
                "explanation": "Analyzes global warehouse capacity and total inventory units on hand across distribution centers.",
                "suggested_chart": "bar",
                "chart_config": {
                    "x_axis": "warehouse_name",
                    "y_axis": "total_units_stored",
                    "title": "Total Units Stored by Warehouse"
                }
            }

        elif any(term in clean_q for term in ["supplier", "vendor", "procurement", "purchase order"]):
            return {
                "sql": """SELECT s.company_name, s.country, s.rating, COUNT(po.id) AS po_count, ROUND(COALESCE(SUM(po.total_cost), 0), 2) AS total_procurement
FROM suppliers s
LEFT JOIN purchase_orders po ON s.id = po.supplier_id
GROUP BY s.id, s.company_name, s.country, s.rating
ORDER BY total_procurement DESC
LIMIT 10""",
                "explanation": "Evaluates suppliers by overall procurement spend and supplier performance ratings.",
                "suggested_chart": "bar",
                "chart_config": {
                    "x_axis": "company_name",
                    "y_axis": "total_procurement",
                    "title": "Top Suppliers by Procurement Volume ($)"
                }
            }

        elif any(term in clean_q for term in ["top customer", "spent the most", "highest spend", "highest spending", "best customer", "most money"]):
            if is_postgres:
                cust_sql = """SELECT c.id, (c.first_name || ' ' || c.last_name) AS customer_name, c.email, c.country, c.loyalty_tier, c.lifetime_spend
FROM customers c
ORDER BY c.lifetime_spend DESC
LIMIT 5"""
                x_axis = "customer_name"
            else:
                cust_sql = """SELECT c.id, c.name, c.email, c.country, ROUND(SUM(o.total_amount), 2) AS total_spent
FROM customers c
JOIN orders o ON c.id = o.customer_id
WHERE o.status = 'completed'
GROUP BY c.id, c.name, c.email, c.country
ORDER BY total_spent DESC
LIMIT 5"""
                x_axis = "name"
            return {
                "sql": cust_sql,
                "explanation": "Finds the top 5 customers with the highest lifetime spend.",
                "suggested_chart": "bar",
                "chart_config": {
                    "x_axis": x_axis,
                    "y_axis": "lifetime_spend" if is_postgres else "total_spent",
                    "title": "Top 5 Customers by Cumulative Spend ($)"
                }
            }
        
        elif any(term in clean_q for term in ["sales trend", "monthly", "revenue by month", "sales over time", "monthly revenue"]):
            date_trunc_expr = "DATE_TRUNC('month', order_date)" if is_postgres else "strftime('%Y-%m', order_date)"
            return {
                "sql": f"""SELECT {date_trunc_expr} AS month, 
       ROUND(SUM(total_amount), 2) AS total_revenue, 
       COUNT(id) AS total_orders
FROM orders
WHERE status NOT IN ('cancelled', 'refunded')
GROUP BY month
ORDER BY month ASC""",
                "explanation": "Calculates monthly sales revenue and order volume over time, excluding cancelled orders.",
                "suggested_chart": "line",
                "chart_config": {
                    "x_axis": "month",
                    "y_axis": "total_revenue",
                    "title": "Monthly Revenue Trend ($)"
                }
            }

        elif any(term in clean_q for term in ["low on stock", "low stock", "running low", "critical stock", "inventory"]):
            return {
                "sql": """SELECT id, name, category, price, stock_quantity, rating
FROM products
WHERE stock_quantity < 50
ORDER BY stock_quantity ASC
LIMIT 10""",
                "explanation": "Lists products with critically low inventory (under 50 units) sorted from lowest to highest stock.",
                "suggested_chart": "bar",
                "chart_config": {
                    "x_axis": "name",
                    "y_axis": "stock_quantity",
                    "title": "Products with Low Stock Quantities"
                }
            }

        elif any(term in clean_q for term in ["order status", "orders by status", "breakdown of orders", "status"]):
            return {
                "sql": """SELECT status, COUNT(id) AS order_count, ROUND(SUM(total_amount), 2) AS total_value
FROM orders
GROUP BY status
ORDER BY order_count DESC""",
                "explanation": "Aggregates orders and cumulative order value grouped by order fulfillment status.",
                "suggested_chart": "pie",
                "chart_config": {
                    "x_axis": "status",
                    "y_axis": "order_count",
                    "title": "Order Distribution by Status"
                }
            }

        elif any(term in clean_q for term in ["category", "categories", "units sold"]):
            if is_postgres:
                cat_sql = """SELECT pc.name AS category_name, 
       ROUND(SUM(oi.line_total), 2) AS category_revenue,
       SUM(oi.quantity) AS units_sold
FROM order_items oi
JOIN products p ON oi.product_id = p.id
JOIN product_categories pc ON p.category_id = pc.id
JOIN orders o ON oi.order_id = o.id
WHERE o.status IN ('completed', 'delivered')
GROUP BY pc.name
ORDER BY category_revenue DESC"""
                cat_x = "category_name"
            else:
                cat_sql = """SELECT p.category, 
       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS category_revenue,
       SUM(oi.quantity) AS units_sold
FROM order_items oi
JOIN products p ON oi.product_id = p.id
JOIN orders o ON oi.order_id = o.id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY category_revenue DESC"""
                cat_x = "category"
            return {
                "sql": cat_sql,
                "explanation": "Calculates total revenue and units sold per product category for completed orders.",
                "suggested_chart": "bar",
                "chart_config": {
                    "x_axis": cat_x,
                    "y_axis": "category_revenue",
                    "title": "Revenue by Product Category ($)"
                }
            }

        elif any(term in clean_q for term in ["recent customer", "list customer", "show customer", "all customer"]):
            if is_postgres:
                c_list_sql = """SELECT id, first_name, last_name, email, country, loyalty_tier, signup_date
FROM customers
ORDER BY signup_date DESC
LIMIT 10"""
            else:
                c_list_sql = """SELECT id, name, email, country, signup_date
FROM customers
ORDER BY signup_date DESC
LIMIT 10"""
            return {
                "sql": c_list_sql,
                "explanation": "Displays the 10 most recently signed-up customers.",
                "suggested_chart": "table",
                "chart_config": {
                    "x_axis": "first_name" if is_postgres else "name",
                    "y_axis": "id",
                    "title": "Recent Customers"
                }
            }

        else:
            return {
                "sql": "",
                "explanation": f"I couldn't identify a database query from '{user_query}'. Please ask a question related to your tables (e.g. customers, products, orders, marketing_campaigns, departments, suppliers, subscriptions), or configure a Gemini/OpenAI API key in Settings.",
                "suggested_chart": "table",
                "chart_config": {}
            }
