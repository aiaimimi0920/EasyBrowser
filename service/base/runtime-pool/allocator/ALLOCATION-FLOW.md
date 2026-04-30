# Allocation Flow Skeleton

Allocator should later follow a normalized sequence:

1. receive provider candidate set
2. inspect current ready runtimes
3. reject runtimes that are:
   - busy
   - cooled
   - failed
   - draining
4. prefer reusable runtime when allowed
5. spawn fresh runtime when:
   - reuse is disallowed
   - no reusable runtime exists
   - capacity permits
6. return normalized allocation result

The allocator should not directly encode provider-specific execution logic.
