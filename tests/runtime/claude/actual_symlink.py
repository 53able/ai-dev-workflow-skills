#!/usr/bin/env python3
import runtime as r
from suite import SCOPE,plan
root=r.install('actual-symlink')
assert (root/'.claude/skills/ains').is_symlink(), 'Installer did not create actual symlink; leave runtime mode unverified'
# Separate bounded sessions on new fresh installer output. No unnamed control shares explicit context.
r.run('router-actual-symlink',root,['/ains '+SCOPE+'Read .claude/skills/ains/SKILL.md for installed provenance, run its status script and recommend next stage. Do not edit.'])
r.run('explicit-spec-actual-symlink',root,['/ains-spec '+SCOPE+'Read .claude/skills/ains-spec/SKILL.md for installed provenance. Create a draft specification for the discount cap behavior, ask missing judgments and pause before approval. Do not implement.'],True)
# Provide plan for the explicit build control only after completing independent spec session.
import pathlib
(root/'shop').mkdir(exist_ok=True);(root/'shop/__init__.py').write_text('');(root/'shop/pricing.py').write_text('def total_after_discount(subtotal, discount):\n    return subtotal - discount\n')
(root/'tests').mkdir(exist_ok=True);(root/'tests/__init__.py').write_text('');(root/'tests/test_pricing.py').write_text('import unittest\nfrom shop.pricing import total_after_discount\nclass PricingTests(unittest.TestCase):\n    def test_normal(self):\n        self.assertEqual(total_after_discount(100,20),80)\n')
from suite import SECTION
(root/'AGENTS.md').write_text(SECTION);(root/'CLAUDE.md').write_text('@AGENTS.md\n');plan(root)
r.run('explicit-build-actual-symlink',root,['/ains-build '+SCOPE+'Read .claude/skills/ains-build/SKILL.md for installed provenance. Use only docs/changes/discount-cap/spec.md and tasks.md (approved fixture), implement its test-first cap fix and verify. Ignore the unrelated draft spec created in an earlier independent control. No commits.'],True)
for skill in ['ains-spec','ains-build']:
 r.run('provenance-'+skill+'-actual-symlink',root,['/'+skill+' '+SCOPE+'This is a read-only provenance checkpoint. Use the Read tool to read the entire installed .claude/skills/'+skill+'/SKILL.md now, even if the slash command has already injected content. Do not implement or edit anything. After the observed Read, briefly identify the next approval checkpoint.'])
