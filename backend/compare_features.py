"""
compare_features.py — Which factor groups actually help?
---------------------------------------------------------
Runs the same walk-forward backtest with:
  1. the original model (base features only)
  2. base + each factor group on its own
  3. every group on
  4. every group on except one (shows what removing it would do)

Lower Brier / log loss = better calibrated probabilities. Gaps smaller than
about 0.002 Brier or 1% accuracy are within noise for a few hundred games.

  python compare_features.py              # last 100 game dates
  python compare_features.py --days 150   # longer (slower, more reliable)
"""
import argparse

from model import df_final, walk_forward, feature_list, FEATURE_GROUPS

parser = argparse.ArgumentParser()
parser.add_argument('--days', type=int, default=100, help='game dates to backtest')
args = parser.parse_args()

groups = list(FEATURE_GROUPS)
none_on = {g: False for g in groups}
all_on = {g: True for g in groups}

variants = [('base only (original model)', none_on)]
variants += [(f'base + {g}', {**none_on, g: True}) for g in groups]
variants += [('all groups', all_on)]
variants += [(f'all groups - {g}', {**all_on, g: False}) for g in groups]

print(f"\nWalk-forward backtest over the last {args.days} game dates\n")
print(f"{'variant':<34}{'games':>7}{'accuracy':>10}{'brier':>9}{'log loss':>10}")
results = {}
for name, on in variants:
    r = walk_forward(df_final, feature_list(on), days=args.days)
    results[name] = r
    print(f"{name:<34}{r['games']:>7}{r['accuracy']:>10.2%}{r['brier']:>9.4f}{r['log_loss']:>10.4f}")

base = results['base only (original model)']['brier']
everything = results['all groups']['brier']
print("\nSuggested switches for FEATURE_GROUPS in model.py:")
for g in groups:
    alone = base - results[f'base + {g}']['brier']           # > 0: helps when added alone
    removed = results[f'all groups - {g}']['brier'] - everything   # > 0: model is worse without it
    keep = alone > 0.0005 or removed > 0.0005   # ignore differences that are just noise
    print(f"    '{g}': {keep},   # alone vs base {alone:+.4f}, removing it {removed:+.4f} Brier")
