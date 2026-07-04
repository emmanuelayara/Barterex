# User Data Export (GDPR) - Implementation Guide

## Overview

A GDPR-compliant user data export endpoint that allows admins to export complete user data as a ZIP file containing structured data files. Users can request their data in compliance with data protection regulations.

## Features

### What Gets Exported

1. **User Profile Data** (JSON)
   - Username, Email, Phone
   - Address, City, State
   - Account creation date and last login
   - Account status and ban information
   - Level, Tier, Trading Points, Credits
   - Email verification status
   - Two-factor authentication status
   - GDPR consent date

2. **Items Listing** (CSV)
   - Item ID and Name
   - Item number and description
   - Category and status
   - Approval and availability status
   - Creation date
   - Rejection reason (if applicable)

3. **Trading History** (CSV)
   - Order ID and Status
   - Total price
   - Order creation and update dates
   - Number of items in order

4. **Activity History** (CSV)
   - Timestamp of each activity
   - Action type
   - Action details
   - IP address of the request

5. **Credit Transactions** (CSV)
   - Transaction ID and Amount
   - Transaction type and description
   - Reason for transaction
   - Balance before and after
   - Transaction date

6. **Export Metadata** (JSON)
   - Export date and time
   - Admin who performed export
   - Summary of exported data
   - Purpose and compliance information

## Endpoint

```
GET /admin/user/<user_id>/export
```

### Authentication
- Admin login required
- CSRF protection enabled

### Parameters
- `user_id` (integer) - The ID of the user whose data to export

### Response
- HTTP 200 - ZIP file download
- HTTP 404 - User not found
- HTTP 302 - Redirect on error

### Response Headers
- `Content-Type: application/zip`
- `Content-Disposition: attachment; filename=user_data_username_YYYYMMDD_HHMMSS.zip`

## File Structure

The generated ZIP file contains:

```
user_data_username_20260102_191926.zip
├── 00_EXPORT_METADATA.json          (Export info)
├── 01_user_profile.json             (Profile data)
├── 02_items_listing.csv             (User's items)
├── 03_trading_history.csv           (User's orders)
├── 04_activity_history.csv          (Login/activity logs)
└── 05_credit_transactions.csv       (Credit history)
```

## Usage

### Admin Interface
1. Navigate to **Users Management**
2. Find the user to export
3. Click the **📥 Download** button (new export icon)
4. ZIP file downloads automatically with all user data

### Example ZIP Contents

**00_EXPORT_METADATA.json:**
```json
{
  "Export Date": "2026-01-02T19:30:00.000000",
  "Exported By Admin": "admin_user",
  "User ID": 123,
  "Username": "john_doe",
  "Email": "john@example.com",
  "Total Items": 15,
  "Total Orders": 8,
  "Total Activity Logs": 156,
  "Total Transactions": 24,
  "Purpose": "GDPR Data Export Request"
}
```

**01_user_profile.json:**
```json
{
  "User ID": 123,
  "Username": "john_doe",
  "Email": "john@example.com",
  "Phone": "555-0123",
  "Address": "123 Main St",
  "City": "Springfield",
  "State": "IL",
  "Account Created": "2025-06-15T10:30:00",
  "Last Login": "2026-01-02T15:45:00",
  "Account Status": "Active",
  "Email Verified": true,
  "Level": 5,
  "Tier": "Intermediate",
  "Trading Points": 2450,
  "Credits": 1200
}
```

## Security Features

✅ **Access Control**
- Admin-only endpoint
- User ID validation
- CSRF token required

✅ **Data Protection**
- ZIP compression
- No sensitive data in filenames
- Temporary buffer (not written to disk)

✅ **Audit Trail**
- All exports logged to audit trail
- Admin ID recorded
- IP address captured
- Action type: `user_data_exported`

✅ **Error Handling**
- Graceful error messages
- Exceptions logged with full stack trace
- User redirected on failure

## Database Queries

The export function queries:
1. `User` table - Profile data
2. `Item` table - User's items
3. `Order` table - User's orders
4. `ActivityLog` table - User's activities
5. `CreditTransaction` table - User's transactions

## Performance Considerations

- **Memory Usage:** ZIP created in-memory buffer, not on disk
- **Database Load:** Minimal (single query per table)
- **File Size:** Typically 100KB-1MB depending on user activity
- **Export Time:** < 1 second for most users

## GDPR Compliance

✅ **Right to Data Portability**
- Users can request all personal data
- Data provided in structured, machine-readable format
- Export includes all related information

✅ **Right to be Forgotten**
- Can be combined with account deletion
- Provides data before deletion

✅ **Consent Tracking**
- GDPR consent date included in export
- Proof of consent available

✅ **Audit Trail**
- All data access logged
- Admin tracking included
- Timestamp and IP recorded

## Implementation Details

### File Format
- **Profile & Metadata:** JSON (human-readable, parseable)
- **Records:** CSV (spreadsheet-compatible, universal)
- **Compression:** ZIP deflate (industry standard)

### Character Encoding
- UTF-8 for all text
- Special characters handled properly
- CSV escape characters included

### Date Format
- ISO 8601 format (YYYY-MM-DDTHH:MM:SS)
- Timezone-aware (UTC)
- Consistent across all files

## Error Handling

| Error | Status | Message | Action |
|-------|--------|---------|--------|
| User not found | 404 | User not found | Redirect to users |
| Permission denied | 403 | Not authorized | Redirect to dashboard |
| Database error | 500 | Error exporting data | Log and redirect |
| Invalid user ID | 400 | Bad request | Redirect to users |

## Logging

All export actions are logged:

**Application Log:**
```
2026-01-02 19:30:15 - routes.admin - WARNING - User data exported - 
User ID: 123, Username: john_doe, Exported by Admin: admin_user, 
IP: 127.0.0.1
```

**Audit Log:**
```
Action: user_data_exported
Target: user (ID: 123, Name: john_doe)
Admin: admin_user
Timestamp: 2026-01-02 19:30:15
Reason: GDPR data export request
```

## Code Location

**Route Handler:** [routes/admin.py](routes/admin.py#L1300) - `export_user_data()`

**UI Integration:** [templates/admin/users.html](templates/admin/users.html#L210)

**Required Imports:**
- `json` - JSON serialization
- `csv` - CSV writing
- `io` - In-memory file operations
- `zipfile` - ZIP creation
- `send_file` - File download
- `ActivityLog` - User activity queries
- `CreditTransaction` - Transaction queries

## Testing

### Test Case 1: Basic Export
1. Navigate to Users page
2. Click export button for any user
3. ZIP file downloads
4. Extract and verify all files present
5. Check data accuracy

### Test Case 2: Empty Data
1. Create new user (no items/orders)
2. Export data
3. Verify files created (with "No data" messages)
4. ZIP still created successfully

### Test Case 3: Large Export
1. Find user with many items/orders
2. Export data
3. Verify file size reasonable
4. Check export time < 2 seconds

### Test Case 4: Audit Log
1. Export user data
2. Check audit log
3. Verify entry shows:
   - Admin username
   - User being exported
   - Timestamp
   - GDPR reason

## Configuration

No special configuration required. Feature uses standard Flask/SQLAlchemy setup.

## Dependencies

**Already Available:**
- Flask (render_template, send_file)
- SQLAlchemy (database queries)
- Jinja2 (templates)
- Python standard library (json, csv, io, zipfile)

**No Additional Packages Needed**

## Troubleshooting

**Issue:** ZIP file won't download
- **Solution:** Check admin permissions, verify user exists

**Issue:** ZIP file corrupted
- **Solution:** Retry export, check disk space on client

**Issue:** Data missing from export
- **Solution:** Check database connectivity, verify user has data

**Issue:** Export takes too long
- **Solution:** Check database performance, verify network connection

## Related Features

- [Maintenance Mode](MAINTENANCE_MODE_IMPLEMENTATION.md) - Can disable exports during maintenance
- [Audit Logging](audit_logger.py) - Tracks all export actions
- [User Management](templates/admin/users.html) - Access export feature

## Future Enhancements

- [ ] Schedule exports for specific times
- [ ] Email export link to user
- [ ] Store export history
- [ ] Format options (XML, PDF)
- [ ] Selective data export
- [ ] Encryption of ZIP file
- [ ] Automatic cleanup of old exports
- [ ] Export notification to user

## References

- [GDPR Right to Data Portability](https://gdpr-info.eu/art-20-gdpr/) - EU Regulation
- [Python ZIP File Documentation](https://docs.python.org/3/library/zipfile.html)
- [CSV Format Specification](https://tools.ietf.org/html/rfc4180)

---

**Status:** 🟢 Production Ready

**Last Updated:** January 2, 2026

**Version:** 1.0
