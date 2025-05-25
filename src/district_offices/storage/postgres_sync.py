#!/usr/bin/env python3
"""
PostgreSQL synchronization using SQLAlchemy.
Handles import from and export to upstream PostgreSQL database.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from .models import (
    PostgreSQLBase, UpstreamMember, UpstreamMemberContact, UpstreamDistrictOffice,
    Member, MemberContact, ValidatedOffice
)
from .sqlite_db import SQLiteDatabase

log = logging.getLogger(__name__)


class PostgreSQLSyncManager:
    """Manages sync operations between PostgreSQL and SQLite."""
    
    def __init__(self, postgres_uri: str, sqlite_db: SQLiteDatabase):
        """Initialize sync manager.
        
        Args:
            postgres_uri: PostgreSQL connection URI
            sqlite_db: SQLiteDatabase instance
        """
        self.postgres_uri = postgres_uri
        self.sqlite_db = sqlite_db
        
        # Create PostgreSQL engine
        self.pg_engine = create_engine(postgres_uri)
        self.PGSession = sessionmaker(bind=self.pg_engine)
    
    def sync_members_from_upstream(self) -> Dict[str, int]:
        """Import members from PostgreSQL to SQLite.
        
        Returns:
            Dict[str, int]: Statistics about the sync
        """
        stats = {"members_synced": 0, "contacts_synced": 0}
        
        # Start sync log
        sync_log = self.sqlite_db.log_sync_operation(
            sync_type='members_import',
            sync_direction='from_upstream',
            records_processed=0,
            status='started'
        )
        
        try:
            pg_session = self.PGSession()
            
            # Get all current members from PostgreSQL
            upstream_members = pg_session.query(UpstreamMember).filter(
                UpstreamMember.currentmember == True
            ).all()
            
            # Sync to SQLite
            for upstream_member in upstream_members:
                member_data = {
                    'bioguideid': upstream_member.bioguideid,
                    'currentmember': upstream_member.currentmember,
                    'officialwebsiteurl': upstream_member.officialwebsiteurl,
                    'name': f"{upstream_member.firstname} {upstream_member.lastname}".strip(),
                    'state': upstream_member.state
                }
                
                self.sqlite_db.upsert_member(member_data)
                stats["members_synced"] += 1
            
            pg_session.close()
            
            # Update sync log
            self.sqlite_db.log_sync_operation(
                sync_type='members_import',
                sync_direction='from_upstream',
                records_processed=stats["members_synced"],
                status='completed'
            )
            
            log.info(f"Synced {stats['members_synced']} members from PostgreSQL")
            
        except Exception as e:
            log.error(f"Error syncing members: {e}")
            self.sqlite_db.log_sync_operation(
                sync_type='members_import',
                sync_direction='from_upstream',
                records_processed=0,
                status='failed',
                error_message=str(e)
            )
            raise
        
        return stats
    
    def sync_contacts_from_upstream(self) -> Dict[str, int]:
        """Import member contacts from PostgreSQL to SQLite.
        
        Returns:
            Dict[str, int]: Statistics about the sync
        """
        stats = {"contacts_synced": 0}
        
        # Start sync log
        sync_log = self.sqlite_db.log_sync_operation(
            sync_type='contacts_import',
            sync_direction='from_upstream',
            records_processed=0,
            status='started'
        )
        
        try:
            pg_session = self.PGSession()
            
            # Get all contacts from PostgreSQL
            upstream_contacts = pg_session.query(UpstreamMemberContact).all()
            
            # Sync to SQLite
            with self.sqlite_db.get_session() as sqlite_session:
                for upstream_contact in upstream_contacts:
                    # Check if member exists in SQLite
                    member = sqlite_session.query(Member).filter_by(
                        bioguideid=upstream_contact.bioguideid
                    ).first()
                    
                    if member:
                        # Upsert contact
                        contact = sqlite_session.query(MemberContact).filter_by(
                            bioguideid=upstream_contact.bioguideid
                        ).first()
                        
                        if contact:
                            contact.contact_page = upstream_contact.contact_page
                            contact.last_synced = datetime.utcnow()
                        else:
                            contact = MemberContact(
                                bioguideid=upstream_contact.bioguideid,
                                contact_page=upstream_contact.contact_page
                            )
                            sqlite_session.add(contact)
                        
                        stats["contacts_synced"] += 1
                
                sqlite_session.commit()
            
            pg_session.close()
            
            # Update sync log
            self.sqlite_db.log_sync_operation(
                sync_type='contacts_import',
                sync_direction='from_upstream',
                records_processed=stats["contacts_synced"],
                status='completed'
            )
            
            log.info(f"Synced {stats['contacts_synced']} contacts from PostgreSQL")
            
        except Exception as e:
            log.error(f"Error syncing contacts: {e}")
            self.sqlite_db.log_sync_operation(
                sync_type='contacts_import',
                sync_direction='from_upstream',
                records_processed=0,
                status='failed',
                error_message=str(e)
            )
            raise
        
        return stats
    
    def export_validated_offices(self, batch_size: int = 100) -> int:
        """Export validated offices from SQLite to PostgreSQL.
        
        Args:
            batch_size: Number of offices to process in each batch
            
        Returns:
            int: Number of offices exported
        """
        exported_count = 0
        
        # Start sync log
        sync_log = self.sqlite_db.log_sync_operation(
            sync_type='offices_export',
            sync_direction='to_upstream',
            records_processed=0,
            status='started'
        )
        
        try:
            # Get unsynced offices
            offices_to_export_orm = self.sqlite_db.get_unsynced_offices()

            if not offices_to_export_orm:
                log.info("No offices to export")
                self.sqlite_db.log_sync_operation(
                    sync_type='offices_export',
                    sync_direction='to_upstream',
                    records_processed=0,
                    status='completed'
                )
                return 0

            # Convert ORM objects to a list of dictionaries to avoid detached instance errors
            offices_data = []
            if offices_to_export_orm: # Ensure there are offices before trying to access attributes
                with self.sqlite_db.get_session() as sqlite_session: # Use a session to ensure objects are attached
                    # Re-query or merge objects into the current session if get_unsynced_offices doesn't guarantee attachment
                    # For simplicity, assuming get_unsynced_offices returns objects that can be read immediately
                    # or are fresh from a session. If not, they would need to be merged.
                    # A safer approach might be to have get_unsynced_offices return dicts directly,
                    # or to re-fetch by ID within this new session.
                    # However, for now, let's try direct attribute access, assuming they are still usable.
                    # A more robust approach if issues persist:
                    # fresh_offices = [sqlite_session.merge(o) for o in offices_to_export_orm]
                    # for office in fresh_offices:
                    # Or, simply re-query:
                    # office_ids_to_sync = [o.office_id for o in offices_to_export_orm]
                    # fresh_offices_to_export = sqlite_session.query(ValidatedOffice).filter(ValidatedOffice.office_id.in_(office_ids_to_sync)).all()
                    
                    # Simpler: Assuming get_unsynced_offices returns usable objects or objects from an active session context
                    # If get_unsynced_offices already uses its own session and closes it, the objects would be detached.
                    # The ideal way is for get_unsynced_offices to either return data dicts, or do its work within a passed session.
                    # Given the current structure, let's fetch by ID again to ensure freshness within this context.
                    
                    office_ids_to_sync = [o.office_id for o in offices_to_export_orm]
                    if office_ids_to_sync: # only query if there are IDs
                        fresh_offices_in_session = sqlite_session.query(ValidatedOffice).filter(
                            ValidatedOffice.office_id.in_(office_ids_to_sync)
                        ).all()

                        for office in fresh_offices_in_session:
                            offices_data.append({
                                "office_id": office.office_id,
                                "bioguide_id": office.bioguide_id,
                                "address": office.address,
                                "suite": office.suite,
                                "building": office.building,
                                "city": office.city,
                                "state": office.state,
                                "zip": office.zip,
                                "phone": office.phone,
                                "fax": office.fax,
                                "hours": office.hours,
                            })
            
            if not offices_data: # Check if there's any data to process after conversion
                log.info("No office data to export after attempting to convert to dictionaries.")
                # Update sync log for no offices
                self.sqlite_db.log_sync_operation(
                    sync_type='offices_export',
                    sync_direction='to_upstream',
                    records_processed=0,
                    status='completed'
                )
                return 0

            pg_session = self.PGSession()

            # Process in batches
            for i in range(0, len(offices_data), batch_size):
                batch_data = offices_data[i:i + batch_size]
                processed_office_ids_in_batch = []

                for office_dict in batch_data:
                    # Create or update in PostgreSQL
                    upstream_office = pg_session.query(UpstreamDistrictOffice).filter_by(
                        office_id=office_dict["office_id"]
                    ).first()

                    if upstream_office:
                        # Update existing
                        upstream_office.bioguide_id = office_dict["bioguide_id"]
                        upstream_office.address = office_dict["address"]
                        upstream_office.suite = office_dict["suite"]
                        upstream_office.building = office_dict["building"]
                        upstream_office.city = office_dict["city"]
                        upstream_office.state = office_dict["state"]
                        upstream_office.zip = office_dict["zip"]
                        upstream_office.phone = office_dict["phone"]
                        upstream_office.fax = office_dict["fax"]
                        upstream_office.hours = office_dict["hours"]
                    else:
                        # Create new
                        upstream_office = UpstreamDistrictOffice(
                            office_id=office_dict["office_id"],
                            bioguide_id=office_dict["bioguide_id"],
                            address=office_dict["address"],
                            suite=office_dict["suite"],
                            building=office_dict["building"],
                            city=office_dict["city"],
                            state=office_dict["state"],
                            zip=office_dict["zip"],
                            phone=office_dict["phone"],
                            fax=office_dict["fax"],
                            hours=office_dict["hours"]
                        )
                        pg_session.add(upstream_office)

                    processed_office_ids_in_batch.append(office_dict["office_id"])

                # Commit PostgreSQL changes
                pg_session.commit()

                # Mark as synced in SQLite
                self.sqlite_db.mark_offices_synced(processed_office_ids_in_batch)

                exported_count += len(batch_data)
                log.info(f"Exported batch of {len(batch_data)} offices")

            pg_session.close()

            # Update sync log
            self.sqlite_db.log_sync_operation(
                sync_type='offices_export',
                sync_direction='to_upstream',
                records_processed=exported_count,
                status='completed'
            )
            
            log.info(f"Successfully exported {exported_count} offices to PostgreSQL")
            
        except Exception as e:
            log.error(f"Error exporting offices: {e}")
            self.sqlite_db.log_sync_operation(
                sync_type='offices_export',
                sync_direction='to_upstream',
                records_processed=exported_count,
                status='failed',
                error_message=str(e)
            )
            raise
        
        return exported_count
    
    def full_sync(self) -> Dict[str, int]:
        """Perform a full sync: import from PostgreSQL, export validated offices.
        
        Returns:
            Dict[str, int]: Statistics about the sync
        """
        stats = {}
        
        # Import members
        member_stats = self.sync_members_from_upstream()
        stats.update(member_stats)
        
        # Import contacts
        contact_stats = self.sync_contacts_from_upstream()
        stats.update(contact_stats)
        
        # Export validated offices
        stats["offices_exported"] = self.export_validated_offices()
        
        return stats