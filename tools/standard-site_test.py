import importlib.util,pathlib,unittest
spec=importlib.util.spec_from_file_location('standard_site',pathlib.Path(__file__).with_name('standard-site.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class KubernetesQuantity(unittest.TestCase):
 def test_extended_kvm_resource_decimal_suffix(self):self.assertEqual(m.quantity('1k'),1000)
 def test_binary_node_memory(self):self.assertEqual(m.quantity('32768Ki'),33554432)
 def test_decimal_exponent(self):self.assertEqual(m.quantity('1e3'),1000)
 def test_reject_fractional_hard_bytes(self):
  with self.assertRaises(ValueError):m.quantity('1m')
 def test_reject_negative_or_overflow(self):
  for value in ('-1','1Ei0','9223372036854775808'):
   with self.subTest(value=value),self.assertRaises(ValueError):m.quantity(value)
if __name__=='__main__':unittest.main()
