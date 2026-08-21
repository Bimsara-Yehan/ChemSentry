"""Co-Storage Association Discovery using mlxtend Apriori and association rules (M3, Lab 09).

Framed as discovery of co-occurring storage patterns, NOT direct hazard classification.
Identified rules are cross-referenced with CAMEO reactivity matrix lookups.
"""

from typing import Any

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

# Sample CAMEO reactivity incompatibility lookup matrix
KNOWN_INCOMPATIBLE_PAIRS = {
    frozenset(
        ["Nitric Acid", "Ethanol"]
    ): "REACTIVE: Strong oxidizer + organic flammable liquid (Fire/Explosion Risk)",
    frozenset(
        ["Sodium Cyanide", "Sulfuric Acid"]
    ): "TOXIC GAS: Cyanide salt + Strong acid releases Hydrogen Cyanide gas",
    frozenset(
        ["Ammonium Nitrate", "Fuel Oil"]
    ): "EXPLOSIVE: Oxidizer + Fuel mixture (ANFO explosive risk)",
}


class CoStoragePatternMiner:
    """Discovers co-stored chemical itemsets across warehouse zones using Apriori (Lab 09)."""

    def __init__(
        self, min_support: float = 0.2, min_threshold_lift: float = 1.0
    ) -> None:
        self.min_support = min_support
        self.min_threshold_lift = min_threshold_lift

    def discover_co_storage_rules(
        self, transactions: list[list[str]]
    ) -> list[dict[str, Any]]:
        """Mine frequent itemsets and association rules from zone co-storage transactions."""
        if not transactions:
            return []

        te = TransactionEncoder()
        te_ary = te.fit(transactions).transform(transactions)
        df = pd.DataFrame(te_ary, columns=te.columns_)

        frequent_itemsets = apriori(df, min_support=self.min_support, use_colnames=True)
        if frequent_itemsets.empty:
            return []

        rules = association_rules(
            frequent_itemsets, metric="lift", min_threshold=self.min_threshold_lift
        )
        discovered_rules = []

        for _, row in rules.iterrows():
            antecedents = list(row["antecedents"])
            consequents = list(row["consequents"])
            combined_pair = frozenset(antecedents + consequents)

            incompatibility_warning = KNOWN_INCOMPATIBLE_PAIRS.get(
                combined_pair, "COMPATIBLE: No known CAMEO reactivity warning."
            )

            discovered_rules.append(
                {
                    "antecedents": antecedents,
                    "consequents": consequents,
                    "support": round(float(row["support"]), 4),
                    "confidence": round(float(row["confidence"]), 4),
                    "lift": round(float(row["lift"]), 4),
                    "incompatibility_status": incompatibility_warning,
                }
            )

        return discovered_rules
