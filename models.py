from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

Base = declarative_base()
engine = create_engine(os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///bookings.db'))
SessionLocal = sessionmaker(bind=engine)

class Booking(Base):
    __tablename__ = 'bookings'
    
    id = Column(Integer, primary_key=True)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=False)  # Added email field
    city = Column(String, nullable=False)
    test_name = Column(String, nullable=False)
    preferred_date = Column(String, nullable=False)
    preferred_time = Column(String, nullable=False)
    collection_type = Column(String, nullable=False)
    booking_datetime = Column(DateTime, nullable=False)

Base.metadata.create_all(engine)

def create_booking(phone, email, city, test_name, preferred_date, preferred_time, collection_type, booking_datetime):
    db = SessionLocal()
    try:
        booking = Booking(
            phone=phone,
            email=email,
            city=city,
            test_name=test_name,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            collection_type=collection_type,
            booking_datetime=booking_datetime
        )
        db.add(booking)
        db.commit()
        return booking
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
