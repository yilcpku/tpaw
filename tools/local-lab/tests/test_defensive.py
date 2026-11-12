import unittest
from tpaw_lab.defensive import Deposit, DefensiveSleeve, GovernmentBond, PartitionedAssets


class DefensiveTests(unittest.TestCase):
    def test_deposit_contract_survives_rate_changes_and_matures_once(self):
        sleeve = DefensiveSleeve(1000, known_deposit_rate=.03, demand_rate=.001, term_months=12)
        sleeve.invest_cash_above(0)
        for _ in range(11):
            sleeve.advance(.01, .02)
        self.assertAlmostEqual(sleeve.deposits[0].annual_rate, .03)
        sleeve.advance(.01, .02)
        self.assertFalse(sleeve.deposits)
        self.assertAlmostEqual(sleeve.cash, 1030)
        sleeve.invest_cash_above(0)
        self.assertEqual(sleeve.deposits[0].annual_rate, .01)

    def test_partial_deposit_break_preserves_rest_and_recognizes_loss(self):
        lot = Deposit(1000, .03, 60, .001, 24)
        before = lot.book_value
        cash, loss = lot.sell(501)
        self.assertAlmostEqual(cash, 501)
        self.assertAlmostEqual(lot.principal, 500)
        self.assertAlmostEqual(cash + lot.book_value + loss, before)
        self.assertAlmostEqual(loss, 29)

    def test_bond_par_coupon_redemption_and_yield_shock(self):
        bond = GovernmentBond(1000, .03, 60)
        self.assertAlmostEqual(bond.price(.03), 1000)
        self.assertLess(bond.price(.06), 1000)
        payments = [bond.advance() for _ in range(60)]
        self.assertEqual(payments[11], 30)
        self.assertEqual(payments[-1], 1030)
        self.assertAlmostEqual(sum(payments), 1150)
        self.assertEqual(bond.price(.03), 0)

    def test_bond_sale_price_matches_mark_and_no_creation(self):
        sleeve = DefensiveSleeve(1000, kind="government_bond", known_government_yield=.03)
        sleeve.invest_cash_above(0)
        sleeve.advance(.02, .08)
        before = sleeve.value
        paid = sleeve.release(500)
        self.assertAlmostEqual(paid + sleeve.value, before)

    def test_current_demand_rate_applies_only_to_broken_principal(self):
        sleeve=DefensiveSleeve(0,deposits=[Deposit(1000,.03,60,.001,24)],demand_rate=.01)
        paid=sleeve.release(510)
        self.assertAlmostEqual(paid,510)
        self.assertAlmostEqual(sleeve.deposits[0].principal,500)
        self.assertEqual(sleeve.deposits[0].annual_rate,.03)
        self.assertAlmostEqual(sleeve.lost_accrued_interest,20)

    def test_semiannual_bond_at_par_and_coupon_timing(self):
        bond=GovernmentBond(1000,.04,120,coupon_period_months=6)
        self.assertAlmostEqual(bond.price(.04),1000)
        payments=[bond.advance() for _ in range(120)]
        self.assertEqual(payments[4],0)
        self.assertEqual(payments[5],20)
        self.assertEqual(payments[-1],1020)
        self.assertAlmostEqual(sum(payments),1400)

    def test_remaining_maturity_curve_pricing_and_sale_conserve(self):
        sleeve=DefensiveSleeve(0,kind="government_bond",government_curve={"12":.01,"60":.05},
                               bonds=[GovernmentBond(1000,.04,60,48)])
        self.assertAlmostEqual(sleeve.value,1040/1.01)
        before=sleeve.value
        paid=sleeve.release(400)
        self.assertAlmostEqual(paid+sleeve.value,before)

    def test_cached_quotes_invalidate_on_curve_change_maturity_and_face_sale(self):
        curve={'12':.01,'60':.05}
        bond=GovernmentBond(1000,.04,60,48)
        sleeve=DefensiveSleeve(0,kind='government_bond',government_curve=curve,bonds=[bond])
        first=sleeve.value;curve['12']=.4  # caller's dict is not the owned snapshot
        self.assertAlmostEqual(sleeve.value,first)
        paid=bond.sell(100,.01);self.assertAlmostEqual(paid+sleeve.value,first)
        sleeve.set_government_curve({'12':.03,'60':.06})
        self.assertAlmostEqual(sleeve.value,bond.face*1.04/1.03)
        bond.advance()
        self.assertAlmostEqual(sleeve.value,bond.face*1.04/1.03**(11/12))

    def test_cash_floor_separate_from_reserve_and_transfer_not_consumption(self):
        account = PartitionedAssets(900, DefensiveSleeve(100), 500, 500)
        before = account.total_value
        result = account.replenish_cash(200)
        self.assertAlmostEqual(result["target"], 300)
        self.assertAlmostEqual(result["equity_sold"], 200)
        self.assertAlmostEqual(account.defensive.cash, 300)
        self.assertAlmostEqual(account.total_value, before)
        self.assertEqual((account.reserve_cash, account.reserve_equity), (500, 500))

    def test_rebalance_invests_cash_above_floor_instead_of_locking_new_income(self):
        account=PartitionedAssets(100,DefensiveSleeve(900),0,0)
        report=account.rebalance_equity(.8,100)
        self.assertAlmostEqual(account.equity,800)
        self.assertAlmostEqual(account.defensive.cash,200)
        self.assertAlmostEqual(account.total_value,1000)
        self.assertAlmostEqual(report['equity_bought'],700)

    def test_rebalance_can_sell_contracts_without_spending_protected_cash(self):
        sleeve=DefensiveSleeve(100,kind='government_bond',known_government_yield=.03,bonds=[GovernmentBond(900,.03,60)])
        account=PartitionedAssets(0,sleeve,0,0)
        account.rebalance_equity(.8,100)
        self.assertAlmostEqual(account.defensive.cash,100)
        self.assertAlmostEqual(account.equity,800)
        self.assertAlmostEqual(account.total_value,1000)

    def test_unfunded_floor_does_not_raid_reserve(self):
        account = PartitionedAssets(50, DefensiveSleeve(100), 1000, 1000)
        result = account.replenish_cash(200)
        self.assertEqual(result["shortfall"], 150)
        self.assertEqual(account.total_value, 2150)

    def test_replenishment_break_loss_is_explicit(self):
        sleeve = DefensiveSleeve(0, deposits=[Deposit(1000, .03, 60, .001, 24)])
        account = PartitionedAssets(0, sleeve, 0, 0)
        before = account.total_value
        result = account.replenish_cash(200)
        self.assertAlmostEqual(before - account.total_value, result["break_interest_lost"])
        self.assertAlmostEqual(account.defensive.cash, 300)

    def test_reserve_equal_draw_reports_short_sleeve(self):
        account = PartitionedAssets(1000, DefensiveSleeve(100), 20, 500)
        result = account.reserve_withdrawal(100)
        self.assertEqual(result["paid"], 40)
        self.assertEqual(result["shortfall"], 60)
        self.assertEqual(account.core_value, 1100)
        self.assertEqual(account.reserve_equity, 480)


if __name__ == "__main__":
    unittest.main()
