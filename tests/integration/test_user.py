# ======================================================================================
# tests/integration/test_user.py
# ======================================================================================
# Purpose: Demonstrate user model interactions with the database using pytest fixtures.
#          Relies on 'conftest.py' for database session management and test isolation.
# ======================================================================================

import pytest
import logging
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.user import User
from tests.conftest import create_fake_user, managed_db_session

# Use the logger configured in conftest.py
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Connection and session tests
# ----------------------------------------------------------------------
 
def test_database_connection(db_session):
    """The database connection works: SELECT 1 should return 1."""
    result = db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
 
 
def test_managed_session():
    """managed_db_session lets us run a query, and a bad query raises an error."""
    with managed_db_session() as session:
        session.execute(text("SELECT 1"))
 
        # A query on a missing table should fail and mention the table name
        try:
            session.execute(text("SELECT * FROM nonexistent_table"))
        except Exception as e:
            assert "nonexistent_table" in str(e)
 
 
def test_session_handling(db_session):
    """
    Partial commits:
      - user1 is saved
      - user2 fails (duplicate email) and is rolled back
      - user3 is saved
      - only user1 and user3 remain
    """
    # The table should start empty (the fixture cleans up after each test)
    assert db_session.query(User).count() == 0
 
    # Save user1
    user1 = User(first_name="Test", last_name="User",
                 email="test1@example.com", username="testuser1",
                 password="password123")
    db_session.add(user1)
    db_session.commit()
    assert db_session.query(User).count() == 1
 
    # CHANGED: use pytest.raises instead of try/except, so the test fails
    # if the duplicate email does NOT raise an error.
    user2 = User(first_name="Test", last_name="User",
                 email="test1@example.com",  # duplicate email
                 username="testuser2", password="password456")
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()  # undo the failed insert
 
    # user1 must still be there after the rollback
    found_user1 = db_session.query(User).filter_by(email="test1@example.com").first()
    assert found_user1 is not None
    assert found_user1.username == "testuser1"
 
    # Save user3
    user3 = User(first_name="Test", last_name="User",
                 email="test3@example.com", username="testuser3",
                 password="password789")
    db_session.add(user3)
    db_session.commit()
 
    # Only user1 and user3 should exist
    emails = {u.email for u in db_session.query(User).all()}
    assert emails == {"test1@example.com", "test3@example.com"}
 
 
# ----------------------------------------------------------------------
# User creation tests
# ----------------------------------------------------------------------
 
def test_create_user_with_faker(db_session):
    """Create one user from fake data and check it was saved."""
    user_data = create_fake_user()
    user = User(**user_data)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)  # reload so the generated id is available
 
    assert user.id is not None
    assert user.email == user_data["email"]
 
 
def test_create_multiple_users(db_session):
    """Create three fake users and check they are all saved."""
    for _ in range(3):
        db_session.add(User(**create_fake_user()))
    db_session.commit()
 
    # CHANGED: check the database count instead of len(list), which only
    # measured the Python list and proved nothing about the database.
    assert db_session.query(User).count() == 3
 
 
# ----------------------------------------------------------------------
# Query tests
# ----------------------------------------------------------------------
 
def test_query_methods(db_session, seed_users):
    """Count, filter, and order users using the seeded data."""
    # Count
    assert db_session.query(User).count() >= len(seed_users)
 
    # Filter by email
    first_user = seed_users[0]
    found = db_session.query(User).filter_by(email=first_user.email).first()
    assert found is not None
 
    # Order by email
    ordered = db_session.query(User).order_by(User.email).all()
    assert len(ordered) >= len(seed_users)
 
 
# ----------------------------------------------------------------------
# Transaction and rollback tests
# ----------------------------------------------------------------------
 
def test_transaction_rollback(db_session):
    """A failed transaction is rolled back, so the new user is not saved."""
    initial_count = db_session.query(User).count()
 
    try:
        db_session.add(User(**create_fake_user()))
        # Force an error before committing
        db_session.execute(text("SELECT * FROM nonexistent_table"))
        db_session.commit()
    except Exception:
        db_session.rollback()
 
    assert db_session.query(User).count() == initial_count
 
 
# ----------------------------------------------------------------------
# Update test
# ----------------------------------------------------------------------
 
def test_update_with_refresh(db_session, test_user):
    """Update a user's email and check updated_at changed."""
    original_email = test_user.email
    original_update_time = test_user.updated_at
 
    test_user.email = f"new_{original_email}"
    db_session.commit()
    db_session.refresh(test_user)  # reload values changed by the database
 
    assert test_user.email == f"new_{original_email}"
    assert test_user.updated_at > original_update_time
 
 
# ----------------------------------------------------------------------
# Bulk insert test (slow)
# ----------------------------------------------------------------------
 
@pytest.mark.slow  # skipped unless you run pytest with --run-slow
def test_bulk_operations(db_session):
    """Insert 10 users at once with bulk_save_objects."""
    users = [User(**create_fake_user()) for _ in range(10)]
    db_session.bulk_save_objects(users)
    db_session.commit()
 
    assert db_session.query(User).count() >= 10
 
 
# ----------------------------------------------------------------------
# Uniqueness constraint tests
# ----------------------------------------------------------------------
 
def test_unique_email_constraint(db_session):
    """Two users with the same email should raise IntegrityError."""
    first_data = create_fake_user()
    db_session.add(User(**first_data))
    db_session.commit()
 
    second_data = create_fake_user()
    second_data["email"] = first_data["email"]  # force a duplicate email
    db_session.add(User(**second_data))
 
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
 
 
def test_unique_username_constraint(db_session):
    """Two users with the same username should raise IntegrityError."""
    first_data = create_fake_user()
    db_session.add(User(**first_data))
    db_session.commit()
 
    second_data = create_fake_user()
    second_data["username"] = first_data["username"]  # force a duplicate username
    db_session.add(User(**second_data))
 
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
 
 
def test_user_persistence_after_constraint(db_session):
    """The original user is still in the database after a duplicate fails."""
    initial_user = User(first_name="First", last_name="User",
                        email="first@example.com", username="firstuser",
                        password="password123")
    db_session.add(initial_user)
    db_session.commit()
    saved_id = initial_user.id
 
    # CHANGED: replaced try / assert False / except with pytest.raises,
    # which is shorter and clearer.
    duplicate_user = User(first_name="Second", last_name="User",
                          email="first@example.com",  # duplicate email
                          username="seconduser", password="password456")
    db_session.add(duplicate_user)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
 
    # The original user must be unchanged
    found_user = db_session.query(User).filter_by(id=saved_id).first()
    assert found_user is not None
    assert found_user.email == "first@example.com"
    assert found_user.username == "firstuser"
 
 
# ----------------------------------------------------------------------
# Error handling test
# ----------------------------------------------------------------------
 
def test_error_handling():
    """Invalid SQL inside managed_db_session should raise an error."""
    with pytest.raises(Exception) as exc_info:
        with managed_db_session() as session:
            session.execute(text("INVALID SQL"))
    assert "INVALID SQL" in str(exc_info.value)
 