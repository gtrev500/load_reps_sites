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
            offices = self.sqlite_db.get_unsynced_offices()
            
            if not offices:
                log.info("No offices to export")
                self.sqlite_db.log_sync_operation(
                    sync_type='offices_export',
                    sync_direction='to_upstream',
                    records_processed=0,
                    status='completed'
                )
                return 0
            
            pg_session = self.PGSession()
            
            # Process in batches
            for i in range(0, len(offices), batch_size):
                batch = offices[i:i + batch_size]
                office_ids = []
                
                for office in batch:
                    # Create or update in PostgreSQL
                    upstream_office = pg_session.query(UpstreamDistrictOffice).filter_by(
                        office_id=office.office_id
                    ).first()
                    
                    if upstream_office:
                        # Update existing
                        upstream_office.bioguide_id = office.bioguide_id
                        upstream_office.address = office.address
                        upstream_office.suite = office.suite
                        upstream_office.building = office.building
                        upstream_office.city = office.city
                        upstream_office.state = office.state
                        upstream_office.zip = office.zip
                        upstream_office.phone = office.phone
                        upstream_office.fax = office.fax
                        upstream_office.hours = office.hours
                    else:
                        # Create new
                        upstream_office = UpstreamDistrictOffice(
                            office_id=office.office_id,
                            bioguide_id=office.bioguide_id,
                            address=office.address,
                            suite=office.suite,
                            building=office.building,
                            city=office.city,
                            state=office.state,
                            zip=office.zip,
                            phone=office.phone,
                            fax=office.fax,
                            hours=office.hours
                        )
                        pg_session.add(upstream_office)
                    
                    office_ids.append(office.office_id)
                
                # Commit PostgreSQL changes
                pg_session.commit()
                
                # Mark as synced in SQLite
                self.sqlite_db.mark_offices_synced(office_ids)
                
                exported_count += len(batch)
                log.info(f"Exported batch of {len(batch)} offices")
            
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