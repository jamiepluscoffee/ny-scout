import os
from datetime import datetime

from peewee import (
    Model, SqliteDatabase, CharField, TextField, FloatField,
    DateTimeField, BooleanField, IntegerField, ForeignKeyField,
    CompositeKey,
)

DB_PATH = os.environ.get("DB_PATH", "data/scout.db")
db = SqliteDatabase(None)


class BaseModel(Model):
    class Meta:
        database = db


class Source(BaseModel):
    name = CharField(unique=True)
    type = CharField()  # ics, json_api, scrape, json_ld
    url = CharField()
    method = CharField(default="requests")  # requests, playwright
    active = BooleanField(default=True)
    parser_version = IntegerField(default=1)
    created_at = DateTimeField(default=datetime.utcnow)


class Event(BaseModel):
    source = ForeignKeyField(Source, backref="events")
    source_event_id = CharField()
    title = CharField()
    description = TextField(default="")
    start_dt = DateTimeField(index=True)
    end_dt = DateTimeField(null=True)
    venue_name = CharField()
    address = CharField(default="")
    neighborhood = CharField(default="")
    lat = FloatField(null=True)
    lon = FloatField(null=True)
    price_min = FloatField(null=True)
    price_max = FloatField(null=True)
    ticket_url = CharField(default="")
    category = CharField(default="")  # jazz, concert, theatre, exhibition
    raw_hash = CharField(default="")
    raw_json = TextField(default="{}")
    first_seen_dt = DateTimeField(default=datetime.utcnow)
    last_seen_dt = DateTimeField(default=datetime.utcnow)
    status = CharField(default="active")  # active, stale, cancelled

    class Meta:
        indexes = (
            (("source", "source_event_id"), True),
        )


class EventEntity(BaseModel):
    event = ForeignKeyField(Event, backref="entities")
    entity_type = CharField()  # artist, exhibition, genre
    entity_value = CharField()


class UserFeedback(BaseModel):
    event = ForeignKeyField(Event, backref="feedback")
    action = CharField()  # like, dislike, save, went
    note = TextField(default="")
    created_dt = DateTimeField(default=datetime.utcnow)


def init_db(db_path=None):
    """Initialize database and create tables."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    db.init(path)
    db.connect(reuse_if_open=True)
    db.create_tables([Source, Event, EventEntity, UserFeedback])
    return db
