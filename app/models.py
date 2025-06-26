from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
from datetime import datetime, timezone


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    search_history = relationship("SearchHistory", back_populates="user")

class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(String(255), nullable=False)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    user = relationship("User", back_populates="search_history")
    results = relationship("Company", back_populates="search")

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    address = Column(Text,nullable=True)
    website = Column(String(255), nullable=True)
    linkedin = Column(String(255),nullable=True)
    founded_year = Column(String(50),nullable=True)
    logo = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    search_id = Column(Integer, ForeignKey("search_history.id"))
    
    search = relationship("SearchHistory", back_populates="results")
    contacts = relationship("Contact", back_populates="company")

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    designation = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(Text)
    linkedin = Column(String(255))
    additional_info = Column(Text)
    company_id = Column(Integer, ForeignKey("companies.id"))
    
    company = relationship("Company", back_populates="contacts")

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "designation": self.designation,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "linkedin": self.linkedin,
            "additional_info": self.additional_info,
        }


# ListContacts model to store the list name
class ListContacts(Base):
    __tablename__ = 'list_contacts'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, unique=True)
    
    # Relationship to the ContactDetail model (One-to-Many)
    contacts = relationship("ContactDetail", back_populates="list")

    def __repr__(self):
        return f"<ListContacts(name={self.name})>"

# ContactDetail model to store individual contact information
class ContactDetail(Base):
    __tablename__ = 'contact_details'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, index=True)
    phone = Column(String, index=True)
    address = Column(String, index=True)
    designation = Column(String)
    additional_info = Column(Text)
    
    # ForeignKey linking ContactDetail to a ListContacts
    list_id = Column(Integer, ForeignKey('list_contacts.id'))
    
    # Relationship to ListContacts (Many-to-One)
    list = relationship("ListContacts", back_populates="contacts")

    def __repr__(self):
        return f"<ContactDetail(name={self.name}, email={self.email})>"
    

class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    chat_id = Column(String, index=True)
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    final_reply = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserLog(Base):
    __tablename__ = "user_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    chat_id = Column(String, index=True)
    message = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # New fields
    total_companies = Column(Integer, nullable=True)
    processed_companies = Column(Integer, nullable=True)
    left_companies = Column(Integer, nullable=True)
