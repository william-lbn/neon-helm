import copy,importlib.util,pathlib,unittest
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
class BootstrapSnapshot(unittest.TestCase):
 def fixture(self):
  node={'metadata':{'name':'worker','uid':'node-original','resourceVersion':'1'},'status':{'capacity':{'memory':'12Gi'},'allocatable':{'memory':'8Gi'}}};binding={'node_name':'worker','node_uid':'node-original','namespace':'product','lease_name':'lease-worker','lease_uid':'lease-original'};profile={'id':'explicit','scheduler_name':'autoscale-scheduler','vm_overhead_bytes':'67108864','pod_overhead_bytes':'16777216'};return node,binding,profile
 def test_metadata_version_does_not_change_approved_bootstrap_domain(self):
  node,binding,profile=self.fixture();first=m.host_bootstrap_row(node,binding,profile,'1073741824');node['metadata']['resourceVersion']='999';node['metadata']['labels']={'example.test/heartbeat':'new'};self.assertEqual(first,m.host_bootstrap_row(node,binding,profile,'1073741824'));self.assertEqual(first['initialize_mode'],'kubernetes-current-snapshot-v1');self.assertNotIn('initialize_at_resource_version',first)
 def test_changed_identity_is_not_adopted(self):
  node,binding,profile=self.fixture();node['metadata']['uid']='replacement'
  with self.assertRaises(RuntimeError):m.host_bootstrap_row(node,binding,profile,'1073741824')
 def test_budget_drift_is_visible_and_configuration_is_copied(self):
  node,binding,profile=self.fixture();first=m.host_bootstrap_row(node,binding,profile,'1073741824');saved=copy.deepcopy(first);node['status']['allocatable']['memory']='9Gi';self.assertNotEqual(first['kubernetes_budget'],m.host_bootstrap_row(node,binding,profile,'1073741824')['kubernetes_budget']);binding['lease_uid']='replacement';profile['id']='changed';self.assertEqual(first,saved)
if __name__=='__main__':unittest.main()
