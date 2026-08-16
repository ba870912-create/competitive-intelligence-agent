from neo4j import AsyncGraphDatabase
import os

class Neo4jClient:
    def __init__(self):
        self.driver = AsyncGraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )

    async def upsert_edge(self, subject, relation, obj, date, source_url):
        query = f"""
        MERGE (s:Entity {{name: $subject}})
        MERGE (o:Entity {{name: $object}})
        MERGE (s)-[r:{relation} {{date: $date, source_url: $source_url}}]->(o)
        """
        async with self.driver.session() as session:
            await session.run(query, subject=subject, object=obj,
                               date=str(date), source_url=source_url)

    async def add_price_point(self, competitor, plan_name, price_text, price_amount, date, source_url):
        """
        Records a price observation as its own timestamped node, rather than
        overwriting the previous value -- this is what lets us later compare
        readings across runs and detect real changes over time. price_amount
        is the extracted numeric value (e.g. 7.0), used for comparison so
        that wording differences between runs don't get misread as a real
        price change.
        """
        query = """
        MERGE (c:Entity {name: $competitor})
        CREATE (p:PricePoint {
            plan_name: $plan_name,
            price_text: $price_text,
            price_amount: $price_amount,
            date: $date,
            source_url: $source_url
        })
        CREATE (c)-[:HAS_PRICE_POINT]->(p)
        """
        async with self.driver.session() as session:
            await session.run(query, competitor=competitor, plan_name=plan_name,
                               price_text=price_text, price_amount=price_amount,
                               date=str(date), source_url=source_url)

    async def get_price_changes(self):
        """
        For each (competitor, plan_name) pair, compares the two most recent
        PricePoint readings by their extracted numeric amount -- not the raw
        text -- so that wording differences (e.g. an extra billing-cycle
        detail) don't get flagged as a price change when the number is
        actually the same.
        """
        query = """
        MATCH (c:Entity)-[:HAS_PRICE_POINT]->(p:PricePoint)
        WHERE p.price_amount IS NOT NULL
        WITH c, p.plan_name AS plan, p ORDER BY p.date DESC
        WITH c, plan, collect(p)[0..2] AS recent
        WHERE size(recent) = 2 AND recent[0].price_amount <> recent[1].price_amount
        RETURN c.name AS competitor, plan AS plan_name,
               recent[1].price_text AS old_price, recent[1].date AS old_date,
               recent[0].price_text AS new_price, recent[0].date AS new_date
        """
        async with self.driver.session() as session:
            result = await session.run(query)
            return [record.data() async for record in result]

    async def query(self, cypher: str, **params):
        async with self.driver.session() as session:
            result = await session.run(cypher, **params)
            return [record.data() async for record in result]