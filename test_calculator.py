import unittest
from economist.calculator import calculate

class TestEconomistCalculator(unittest.TestCase):
    def test_calculate_avoids_double_counting_co2(self):
        # Default config profile
        report = calculate(
            building_id="TEST_001",
            floor_area_m2=500.0,
            floors=4,
            transport_km=50.0
        )
        
        # 1. Verification of the double-count fix in standard charts
        dem_impact = report.demolition_impact
        rest_impact = report.restoration_impact
        
        # New Build All-In footprint
        new_build_all_in = rest_impact.co2_new_build_t
        # Demolition Transport footprint
        transport_only = dem_impact.co2_transport_t
        
        # Total Demolition Path footprint should be transport + all_in
        expected_total_demolition_co2 = round(transport_only + new_build_all_in, 1)
        
        # Check standard chart representation
        dem_path_chart_data = None
        co2_chart = report.charts["co2_comparison"]
        for trace in co2_chart["data"]:
            if trace["name"] == "Demolition + New Build":
                dem_path_chart_data = trace["y"][0]
                break
                
        self.assertIsNotNone(dem_path_chart_data)
        self.assertEqual(
            dem_path_chart_data, 
            expected_total_demolition_co2,
            "Chart must not double count new build elements by adding core struct co2 to all_in co2."
        )

        # 2. Verification of proper transport impact tracking in savings
        # Savings = (Transport + New Build All-In) - Restoration
        expected_savings = (transport_only + new_build_all_in) - rest_impact.co2_restoration_t
        
        self.assertAlmostEqual(
            rest_impact.co2_saved_t,
            expected_savings,
            places=1,
            msg="Savings must account for avoided demolition transport CO2."
        )

if __name__ == '__main__':
    unittest.main()
