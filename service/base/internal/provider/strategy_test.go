package provider

import "testing"

func TestStrategyScoreDetailedLatencyBreakdown(t *testing.T) {
	result := StrategyScoreDetailed(StrategyScoreInput{
		Profile:        "latency-first",
		ProviderID:     "chrome",
		Action:         "open_resource",
		ResourceKind:   "page",
		RuntimeReuse:   "prefer_reuse",
		ReadyRuntimes:  2,
		RecentFailures: 1,
		TotalFailures:  3,
	})

	if result.Breakdown.BaseScore != 110 {
		t.Fatalf("expected base score 110, got %d", result.Breakdown.BaseScore)
	}
	if result.Breakdown.ProfileBonus != 30 {
		t.Fatalf("expected profile bonus 30, got %d", result.Breakdown.ProfileBonus)
	}
	if result.Breakdown.ReuseBonus != 240 {
		t.Fatalf("expected reuse bonus 240, got %d", result.Breakdown.ReuseBonus)
	}
	if result.Breakdown.ReadyRuntimeBonus != 160 {
		t.Fatalf("expected ready runtime bonus 160, got %d", result.Breakdown.ReadyRuntimeBonus)
	}
	if result.Breakdown.RecentFailurePenalty != -45 {
		t.Fatalf("expected recent failure penalty -45, got %d", result.Breakdown.RecentFailurePenalty)
	}
	if result.Breakdown.TotalFailurePenalty != -24 {
		t.Fatalf("expected total failure penalty -24, got %d", result.Breakdown.TotalFailurePenalty)
	}
	if result.Score != 471 {
		t.Fatalf("expected score 471, got %d", result.Score)
	}
}

func TestStrategyScoreDetailedRequireReusePenalty(t *testing.T) {
	result := StrategyScoreDetailed(StrategyScoreInput{
		Profile:       "balanced",
		ProviderID:    "chrome",
		Action:        "open_resource",
		ResourceKind:  "page",
		RuntimeReuse:  "require_reuse",
		ReadyRuntimes: 0,
	})

	if result.Breakdown.ReuseBonus != -500 {
		t.Fatalf("expected require_reuse penalty -500, got %d", result.Breakdown.ReuseBonus)
	}
	if result.Score != -400 {
		t.Fatalf("expected total score -400, got %d", result.Score)
	}
}
