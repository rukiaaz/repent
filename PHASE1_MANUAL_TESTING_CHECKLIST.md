# Phase 1 Manual Testing Checklist

This checklist provides manual testing steps to verify the Phase 1 critical integrations are working correctly.

## Database Integration Testing

### 1. Write Queue Integration
**Status**: Implemented in main.py

**Testing Steps**:
1. Start the bot with `python main.py`
2. Check startup logs for: `Database write queue initialized`
3. Perform some database operations (create warnings, log actions)
4. Monitor logs to ensure no database lock errors
5. Stop the bot gracefully
6. Check logs for: `Database write queue stopped`

**Expected Results**:
- [ ] Write queue initializes successfully on startup
- [ ] Database operations complete without lock errors
- [ ] Write queue stops gracefully on shutdown
- [ ] No "database is locked" errors in logs

**Rollback Plan**: If issues occur, remove write queue initialization from main.py

---

### 2. Health Monitor Integration
**Status**: Implemented in main.py

**Testing Steps**:
1. Start the bot with `python main.py`
2. Check startup logs for: `Database health monitor initialized`
3. Let the bot run for 5-10 minutes
4. Check logs for health monitoring output
5. Stop the bot gracefully
6. Check logs for: `Database health monitor stopped`

**Expected Results**:
- [ ] Health monitor initializes successfully on startup
- [ ] Health metrics are logged periodically
- [ ] Health monitor stops gracefully on shutdown
- [ ] No errors related to health monitoring

**Rollback Plan**: If issues occur, remove health monitor initialization from main.py

---

### 3. Channel Rename Tracker Integration
**Status**: Implemented in antinuke.py

**Testing Steps**:
1. Start the bot with `python main.py`
2. Join a test server where bot has admin permissions
3. Rename a channel (e.g., rename "general" to "general-test")
4. Rename it back to "general"
5. Rename it again to "general-test2"
6. Check logs for channel rename tracking messages
7. Try to rename 4+ channels quickly to test threshold

**Expected Results**:
- [ ] Channel renames are tracked per user
- [ ] Threshold detection works (default: 3 renames in 30 seconds)
- [ ] Punishment triggers when threshold exceeded
- [ ] Logs show channel rename tracking activity
- [ ] No rate limit errors from rename tracking

**Rollback Plan**: If issues occur, remove rename tracker from antinuke.py

---

### 4. Cache Warming Implementation
**Status**: Implemented in main.py

**Testing Steps**:
1. Start the bot with `python main.py`
2. Check startup logs for: `Warming cache with guild data...`
3. Check for: `Cache warming complete: X/Y guilds cached`
4. Perform some operations that use cached data
5. Monitor performance of initial operations

**Expected Results**:
- [ ] Cache warming starts during startup
- [ ] Guild data is cached successfully
- [ ] Cache warming completes without errors
- [ ] Initial operations are faster due to warmed cache
- [ ] No errors during cache warming

**Rollback Plan**: If issues occur, remove cache warming call from on_ready

---

## Restore System Testing

### 5. Consecutive Attack Detection
**Status**: Logic tested via unit tests, needs integration testing

**Testing Steps**:
1. Start the bot in a test server
2. Trigger an antinuke event (e.g., delete a channel)
3. Wait 1 minute
4. Trigger another antinuke event
5. Wait 1 minute
6. Trigger a third antinuke event
7. Check if emergency mode is activated
8. Check logs for consecutive attack detection

**Expected Results**:
- [ ] First attack is punished normally
- [ ] Second attack is punished normally
- [ ] Third attack triggers emergency mode
- [ ] Logs show consecutive attack detection
- [ ] Protected snapshot is created

**Manual Test Note**: This requires test server and may be destructive. Use with caution.

---

### 6. Multi-Snapshot Selection
**Status**: Logic tested via unit tests, needs integration testing

**Testing Steps**:
1. Create manual snapshot: `/snapshot create` (if available)
2. Wait 2 minutes
3. Delete some channels
4. Wait 1 minute
5. Delete more channels
6. Trigger restore: `/antinuke restore` (if available)
7. Check which snapshot was used for restore
8. Verify correct channels were restored

**Expected Results**:
- [ ] Restore uses snapshot before first attack
- [ ] All channels from both attacks are restored
- [ ] Channels are restored in correct categories
- [ ] Logs show which snapshot was selected

**Manual Test Note**: This is destructive. Use test server only.

---

### 7. Category-First Restoration
**Status**: Logic tested via unit tests, needs integration testing

**Testing Steps**:
1. Create a category with multiple channels
2. Take a snapshot
3. Delete the entire category
4. Trigger restore
5. Check restoration order

**Expected Results**:
- [ ] Category is recreated first
- [ ] Channels are recreated inside category
- [ ] Channels maintain correct positions
- [ ] No errors during restoration

**Manual Test Note**: This is destructive. Use test server only.

---

### 8. Role Hierarchy Restoration
**Status**: Logic tested via unit tests, needs integration testing

**Testing Steps**:
1. Create multiple roles with specific hierarchy
2. Take a snapshot
3. Delete all roles except @everyone
4. Trigger restore
5. Check role hierarchy

**Expected Results**:
- [ ] Roles are recreated in correct order
- [ ] Role positions are correct
- [ ] @everyone is not recreated (skipped)
- [ ] Role hierarchy is maintained

**Manual Test Note**: This is destructive. Use test server only.

---

## General Bot Testing

### 9. Bot Startup
**Status**: All integrations added

**Testing Steps**:
1. Ensure all dependencies are installed
2. Configure .env file with required variables
3. Run `python main.py`
4. Monitor startup sequence
5. Check for any errors in logs/error.log

**Expected Results**:
- [ ] Bot starts without errors
- [ ] All cogs load successfully
- [ ] Database initializes properly
- [ ] Write queue initializes
- [ ] Health monitor initializes
- [ ] Cache warming completes
- [ ] Bot connects to Discord
- [ ] Commands sync successfully

---

### 10. Bot Shutdown
**Status**: All integrations added

**Testing Steps**:
1. Start the bot and let it run for a few minutes
2. Trigger bot shutdown (Ctrl+C or kill signal)
3. Monitor shutdown sequence
4. Check logs for graceful shutdown messages

**Expected Results**:
- [ ] Shutdown process starts gracefully
- [ ] Write queue stops and drains
- [ ] Health monitor stops
- [ ] Cache layer stops
- [ ] Database connections close
- [ ] Discord connection closes
- [ ] No errors during shutdown
- [ ] All resources cleaned up properly

---

## Performance Testing

### 11. Database Performance
**Status**: Write queue integrated

**Testing Steps**:
1. Start the bot
2. Perform 50+ rapid database operations (create warnings, log actions)
3. Monitor response times
4. Check for any lock errors
5. Compare with previous performance (if available)

**Expected Results**:
- [ ] Operations complete quickly
- [ ] No database lock errors
- [ ] Write queue batches operations
- [ ] Performance improved over previous version
- [ ] No "database is locked" errors

---

### 12. Cache Performance
**Status**: Cache warming added

**Testing Steps**:
1. Start the bot
2. Check cache warming logs
3. Perform operations that use cached data
4. Monitor cache hit rates
5. Compare performance with/without cache warming

**Expected Results**:
- [ ] Cache warming completes successfully
- [ ] Cache hit rate is high (>80%)
- [ ] Operations are faster with warmed cache
- [ ] No cache-related errors
- [ ] Memory usage is reasonable

---

## Error Handling Testing

### 13. Rate Limit Handling
**Status**: Webhook rate limiting fixed

**Testing Steps**:
1. Start the bot
2. Create multiple webhook messages rapidly
3. Monitor for 429 errors
4. Check error logs for rate limit handling
5. Verify webhook caching is working

**Expected Results**:
- [ ] No 429 errors in logs
- [ ] Webhook caching reduces API calls
- [ ] Rate limiting prevents API abuse
- [ ] Errors are handled gracefully
- [ ] Bot continues operating normally

---

### 14. Database Error Recovery
**Status**: Write queue with retry logic

**Testing Steps**:
1. Start the bot
2. Simulate database lock (if possible)
3. Perform database operations
4. Monitor retry behavior
5. Verify operations complete after retry

**Expected Results**:
- [ ] Write queue retries failed operations
- [ ] Operations complete after retry
- [ ] Exponential backoff is used
- [ ] No data loss due to transient errors
- [ ] Logs show retry attempts

---

## Integration Testing Summary

### Critical Tests (Must Pass)
- [ ] Write queue initializes and operates correctly
- [ ] Health monitor initializes and operates correctly
- [ ] Channel rename tracker integrates properly
- [ ] Cache warming completes successfully
- [ ] Bot starts and shuts down gracefully
- [ ] No database lock errors
- [ ] No 429 API errors

### Important Tests (Should Pass)
- [ ] Restore system logic works correctly
- [ ] Performance improvements are evident
- [ ] Error handling works correctly
- [ ] Cache performance is good

### Optional Tests (Nice to Have)
- [ ] Manual restore testing (destructive)
- [ ] Consecutive attack detection (destructive)
- [ ] Category-first restoration (destructive)
- [ ] Role hierarchy restoration (destructive)

---

## Testing Environment Requirements

### Test Server Setup
- Discord server with bot having admin permissions
- Test channels and roles that can be deleted/recreated
- No production data (use dedicated test server)

### Tools Required
- Python 3.11+
- Discord bot token
- Database access
- Log monitoring capability

### Safety Precautions
- Never test in production servers
- Always use test server for destructive tests
- Backup database before testing restore functionality
- Have rollback plan ready for each integration

---

## Success Criteria

Phase 1 is considered complete when:
- [x] All database integrations are implemented
- [ ] All unit tests pass
- [ ] Bot starts and shuts down gracefully
- [ ] No critical errors in logs
- [ ] Performance improvements are evident
- [ ] Rate limiting issues are resolved
- [ ] Manual critical tests pass

---

## Next Steps

After Phase 1 testing is complete:
1. Document any issues found
2. Create rollback procedures if needed
3. Proceed to Phase 2 (Feature Completion)
4. Continue monitoring in production
5. Address any issues that arise