from sqlalchemy import Column, String, Date, JSON, Integer, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

Base = declarative_base()

class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    week_of = Column(Date)
    edges_json = Column(JSON)

class BriefHistory(Base):
    __tablename__ = "brief_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    week_of = Column(Date)
    brief_json = Column(JSON)

engine = create_engine(os.environ["POSTGRES_URL"])
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)