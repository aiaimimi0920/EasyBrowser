# Mode Rules Skeleton

## Strategy Mode

Expected behavior:

- route chosen by policy
- provider may be changed by runtime conditions
- fallback may happen automatically before execution starts

## Direct Mode

Expected behavior:

- caller or operator explicitly selects provider
- strategy ranking is bypassed
- cooldown rules may still apply unless an explicit operator override is later
  designed
