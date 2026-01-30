# Shared Error Handling Guidelines

## Severity Levels

| Level | Code | Action | Human Required |
|-------|------|--------|----------------|
| Critical | CRIT | Halt immediately, rollback if possible | Yes |
| Error | ERR | Halt current stage | Yes |
| Warning | WARN | Log and continue | No |
| Info | INFO | Log only | No |

## Error Response Format

```json
{
  "severity": "critical|error|warning|info",
  "code": "<ERROR_CODE>",
  "message": "<human readable message>",
  "context": {
    "stage": "<current stage>",
    "source": "<data source>",
    "item": "<affected item id if applicable>"
  },
  "recoverable": true/false,
  "suggestedActions": [
    "<action 1>",
    "<action 2>"
  ]
}
```

## Common Error Codes

### Data Errors (1xxx)
- `ERR_1001`: Missing required field
- `ERR_1002`: Invalid field value
- `ERR_1003`: Duplicate identifier
- `ERR_1004`: Invalid reference
- `ERR_1005`: Circular dependency

### Connection Errors (2xxx)
- `ERR_2001`: Connection failed
- `ERR_2002`: Authentication failed
- `ERR_2003`: Timeout
- `ERR_2004`: Rate limited

### Transform Errors (3xxx)
- `ERR_3001`: Unmappable item type
- `ERR_3002`: Property conversion failed
- `ERR_3003`: Relationship target not found

### Integration Errors (4xxx)
- `ERR_4001`: Node conflict
- `ERR_4002`: Edge conflict
- `ERR_4003`: Consistency violation
- `ERR_4004`: Snapshot failed

## Recovery Strategies

### On Critical Error
1. Log full error context
2. Create snapshot of current state (if possible)
3. Halt all processing
4. Add to human intervention queue
5. Preserve partial results for analysis

### On Error
1. Log error with context
2. Mark current stage as failed
3. Add issue to tracker
4. Halt current stage (not entire pipeline)
5. Allow manual retry after resolution

### On Warning
1. Log warning with context
2. Add to run report
3. Continue processing
4. Review warnings in final report

## Rollback Guidelines

When rollback is required:
1. Restore from most recent pre-stage snapshot
2. Mark affected tasks as "rolled back"
3. Log all changes that were reverted
4. Update issue tracker with rollback info
