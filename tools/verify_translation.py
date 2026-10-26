#!/usr/bin/env python3
"""Offline structural translation proof against an explicit immutable baseline.

This does not prove semantic equivalence or native routing. Independent review is
required. No scripts from either tree are imported or executed.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

BASE_COMMIT = "2c0960885926075502a319a19eafbed901690dde"
BASE_MANIFEST = "4d766b7ce83e730a1cbd767b5ddae1c8c2b2c08d8330564e87747b372248b4f4"
CYRILLIC = re.compile(r"[\u0400-\u052f\u2de0-\u2dff\ua640-\ua69f\u1c80-\u1c8f\ufe2e-\ufe2f\U0001e030-\U0001e08f]")
ALLOWLIST = [{'path': 'README.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '8f16010a73cbffe073c868cffff3db9c595b9e676c6ab9ead53b9c56380b56f9'},
 {'path': 'docs/guides/ai-assisted-onboarding.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'f64e298c5b1a028c0aad9be0a000543f0c157de84a616d0657a1e2ec90380605'},
 {'path': 'ai-factory/ai-factory-plan.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '961255d4718dc37ace525950293a5ca52cc3fda497ddf8036b54bd272668bb22'},
 {'path': 'ai-factory/crg.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'bec10ca22900408cec62250bbb18f4c15c3365271cfd239c4a92ac02b59de064'},
 {'path': 'ai-factory/feature-lifecycle.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'c3f82ebdeff7f79ecd6c24137d80f79b30299e135d2a4fc3688b989ffa2e95e8'},
 {'path': 'ai-factory/models.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'c8f251577d27f8dbce6a7a4eda32c48617560758be4a0ad068c7d232ad2da3e7'},
 {'path': 'ai-factory/onboarding.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '16ce883d0ac1bf9904a86486958090a1fea2628e6d3141b129c49ed10682c6d7'},
 {'path': 'ai-factory/onboarding/change-protocol.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'cfd18d18725d0b8445219db207bc9f289ec82c0a6647f21e13fa45533128b39a'},
 {'path': 'ai-factory/review-handoff.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'a3ed135777e878d1fb3be57670220ec3a862a826f7ba4a189b891d65330a2c52'},
 {'path': 'ai-factory/roadmap.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '2ead4263500e6f0453d14f4484e34060566978302470ad00138531dafc11bbc4'},
 {'path': 'ai-factory/status.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '30e82f97199f7d51b33a4677031240a8ba3e98b88d6e25dcf4d7e6f48ed8e9f6'},
 {'path': 'ai-factory/workflow.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'a579ea49c63f9079848009f3400acbb216bf499bde07e0a8e379f3f93aa42d68'},
 {'path': 'rules/README.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'd9200b675e715989f96f1699b7c50a57a313005269d4b5929df91b8ea9333ccc'},
 {'path': 'rules/agent-entry.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'b0f4fd7eb84fb502f2744b71a34c4331805222002d9d15d0ca543a78c219c8b3'},
 {'path': 'rules/subagent-orchestration-ledger.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '60e7a91e747397663b223c69b728a401760c7db10aa836a4da78f365a9ecaf61'},
 {'path': 'templates/acceptance-full.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '3e506d139eb803242c355781cffd779b3ee729be481566760e403a9caa325887'},
 {'path': 'templates/acceptance-portable.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'f3be85ae9f143132cfc7bc1a11a4cb522e3b3065e0ca1437d0a0b7bb5e157080'},
 {'path': 'templates/adapter-full.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '0ffab0ef59cbab76005e929bebd7c749d65ffd6627cd2bd0d11a45ca99930ede'},
 {'path': 'templates/adapter-portable.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '4053f76f64371825cf39b8d330186b90ee1073bdc1b83ff4367f6cc730552ad3'},
 {'path': 'adapters/legacy-planning/acceptance-spec-portable.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'ceca38986a6f05a58697adeee71f3129ca651ae19077c08bae30140991c38d86'},
 {'path': 'adapters/legacy-planning/cto-research-portable.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'fb06f1eb35ebeb710015a756ea5722b75da49dc207769f4aa17d0bb45ff9fdde'},
 {'path': 'adapters/legacy-planning/plan-critique-portable.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '6708304a5a419c1161dad41db8137a036dac1acf56f7069b6a75f74bc124582c'},
 {'path': 'adapters/legacy-planning/plan-defense-portable.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '17b809b3ec7bf738e4e76110286a6ed8445e084e77f48990e593e768dadb287a'},
 {'path': 'docs/portable/change-protocol.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'a898f790e765251e08cd709209e39fd7aec0637355b1f3a6b39cf3ba62eeac2c'},
 {'path': 'docs/portable/crg.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '7ea100c443861d2853fa35dabb6f9265ac1d9457ee3dea07673005ef00e20834'},
 {'path': 'docs/portable/models.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '8dc2ea5bb66314f62d54348593c9d27b991099ff38c6b98564b3dcf963b2b0aa'},
 {'path': 'docs/portable/review-handoff.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': '8f25f908eb545d6ff19909812e11cb4442cdcfb90a7e4432e8bf8fbdc0cf67b2'},
 {'path': 'docs/legacy/ai-factory-plan-entry.md',
  'operation': 'modify',
  'class': 'current_docs',
  'before_sha256': 'd83984fef0a79373f95b5c84fda5a7d680df9bce46b526353a0b116951d529a7'},
 {'path': 'skills/anti-slop-design/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '605ced0506c7f3e8f18ee0b48a4749148b0f430164c48a2faa66cf02b2e156b1'},
 {'path': 'skills/arch/caveman/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '08c8bc7fa34e845859792257bc520ee42e13f796e1c5dd07888c365143420ce9'},
 {'path': 'skills/arch/code-review/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '79b3bc354ebbef41ba39c2d927ac2b4910dbf4e32f8e65e8778b981f061fa92d'},
 {'path': 'skills/arch/codebase-design/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '25d4efdb9957cdfc1eeb6a7d754c1cb1673be4c72591bda4ed1c18d875380574'},
 {'path': 'skills/arch/diagnosing-bugs/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '8778ed54406ac7c591173f68ae79a530e8a6eda463f9188791400cdd993f42e3'},
 {'path': 'skills/arch/domain-modeling/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '320f20a8c69ac2177b5a505f3479672d481a0523d4e782b386d0db0bc224b9fc'},
 {'path': 'skills/arch/improve-codebase-architecture/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'bb7cafd4b591a1cc2101730b251cf2f731aefdb7f05aff43d27e8cda6fe5283b'},
 {'path': 'skills/arch/receiving-code-review/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '5eaef373ed020a0cca682329d02a3c8cb4acd59c5f054a112f348652ad99512c'},
 {'path': 'skills/arch/tdd/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'd02a74d590cc4d7b437a95efeee3bf762fb95a8a2494b934ae0bc3085a78a620'},
 {'path': 'skills/crg/crg-debug-issue/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '01577f9a19f0636a6f81c59414c5a9aa4de76814c6c21d555aba70c8637a176b'},
 {'path': 'skills/crg/crg-explore-codebase/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '7e6170a80cbffab15776941106a599fa0064ce1802058f8232e2c2ec080a46fb'},
 {'path': 'skills/crg/crg-refactor-safely/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'ef93e2915086a04ec6beab757dd4140bccba4cf47d997b7560b20c019acdd3d4'},
 {'path': 'skills/crg/crg-review-changes/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '5c01719daaf262e5f687e58c8d07863629329f40ea2913eb4166c439de75941f'},
 {'path': 'skills/deliver/implement-spec/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '929d7bbac4601276ec84038ce4ed925592bb82bc56f576a0337b5cd60dfec4ba'},
 {'path': 'skills/deliver/implement/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '1e7cdd434dc6b42c13f9b9b0bbc1f4176835084c6d6d1867ef9339c2e90ecc36'},
 {'path': 'skills/deliver/spec-flow/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '5809c7a8c53b13d2bbcca2788c641c3dc56ebe670ed376059f323d8118675e57'},
 {'path': 'skills/deliver/to-spec/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '4cdc224d25916ad2e1dd83b2ee1a10f881b7555632b2d860173712848babb137'},
 {'path': 'skills/deliver/to-tickets/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '918b36d4ff0e797eaead9bfdddabdfc0d3767d0f8f6a0e6c594ef014a0e0c06f'},
 {'path': 'skills/deliver/triage/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '8b4069926b2895ebda1065b4174dbbc605338ad627fc99da31ba1b2f3c67a06e'},
 {'path': 'skills/deliver/wayfinder/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '218c4337722a9311405144b7e48af7417643ac1dec2352bbf256cbd4f82a5cf2'},
 {'path': 'skills/design-pass/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '264655dfa9ae6d43441e5099309e5c9e46e89c39e857a8775ffa3c5ef31baf34'},
 {'path': 'skills/design-pass/references/viewport-coverage.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'f11b42f76cbe6b873b681202417c2a0ebbe4d1774e329fd9ffbb9b91fcf64882'},
 {'path': 'skills/entity-e2e-coverage/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '5183ae07f775e28afa6662c3292c7d6a9e71f19c6d86f41b1ccaeacdfc17fac2'},
 {'path': 'skills/entity-e2e-coverage/references/matrix.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '648ab6d93481e8695a752b2b18d725b9dd21635c5ba52b1f1d38257539e79a9a'},
 {'path': 'skills/entity-e2e-coverage/references/testing-rules.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'c82fe9da2a455ef45826765bd777e05dfe21c15250d89662b0729b7705487dfe'},
 {'path': 'skills/git/git-guardrails-claude-code/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'b4709281785acbfecf7dde8461e94a2a59cf5e94fe5b081b94fdd5853248cb8d'},
 {'path': 'skills/git/pr/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '87b313b80245008807efcdb3908d3a70f162ed55ea076c031185f7138f3d4c92'},
 {'path': 'skills/git/resolving-merge-conflicts/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'dcfa55d6d1499649e2d16c6bab7118bc83e5edfc3ee3a376869d11c4bba706bf'},
 {'path': 'skills/git/setup-pre-commit/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '3a5ed5c3c50cda6df9c35b4c34b6c03e30132e611332ce11b6efd24ec881c9eb'},
 {'path': 'skills/interface-review/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '771af98176b444f76162f9b7bd72910a8d230976e28a6fe464f29b71cb3aae18'},
 {'path': 'skills/pattern-architecture-review/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'ea547aa56bd0af1ecadd26fb206134cc17f2a2dd8e8aea50ceaa6253b9a55966'},
 {'path': 'skills/plan/acceptance-spec/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'ff7d07cca0c28980c58ee8ca83d0283830ea93a2c2a157a29b37e02a7874fed4'},
 {'path': 'skills/plan/ask-matt/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '3322c8a6efca04a193a933093c7d7d0c2a802b1b87edd73b2a70212846aa48c0'},
 {'path': 'skills/plan/cto-agenda/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '6647a0d4c831fef9cf0613d469757b5cd6b4800d6c305ff5d27a0dc9e79fb234'},
 {'path': 'skills/plan/cto-research/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'b7cb8f3c8b3c369df2e8fc7e773313147ceda4666f9b4c1b5b713c42c7fea814'},
 {'path': 'skills/plan/grill-me/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '59353f1fb13b77c720c2fa4b93144396fe9d2e9afc189e732173b08ddbf2af21'},
 {'path': 'skills/plan/grill-with-docs/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'a2ec16b4d2c87c1e307b6148057a0bdb1b5d4b29e2be415a19d1e92c6009d270'},
 {'path': 'skills/plan/grilling/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'd5e2b6efa11cb7fabc5e170ff70a0f6052a29b29f25e4550ba2f4a905b375ed5'},
 {'path': 'skills/plan/plan-critique/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '2da18d121267b4ad53b248e6d61f7bfe4b8bd03d0cedce2819bb759ede38b840'},
 {'path': 'skills/plan/plan-defense/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '11d1d73ab06cbe44cd3aac4f45fb58a632f415ea89d24959d8234f27b018da6a'},
 {'path': 'skills/plan/to-questionnaire/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '7b55348a99e76fd11a1d18311fdc848c828e3b904250725fa577467b0d8c49eb'},
 {'path': 'skills/pt/ponytail-audit/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '6a320e541f6db4f3a89e56275d4c2f095db77b39a4e4c9d996335bb8ab6087f7'},
 {'path': 'skills/pt/ponytail-debt/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '6c4943f0fa7cb7db9bceb432560aed631c785a91e607ed414ebacf8a6dca5e55'},
 {'path': 'skills/pt/ponytail-gain/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '7d32eff3bbb571bf9f78899fb64eb195848015c493cfaa1df68184b48bfe0d38'},
 {'path': 'skills/pt/ponytail-help/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'd276824909822db400e04ca12c868b8b2c913ef0bf0015700f980c7986233878'},
 {'path': 'skills/pt/ponytail-review/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '5bf501d4aeaabe1086ac32767a34bd0ed2029be219e816fd5c8f9f67cdb526de'},
 {'path': 'skills/pt/ponytail/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '70b69cf6bb9e6be4fe8b734bded40cfff09fbab010bb451660227c914a1858f2'},
 {'path': 'skills/reference-ui-reconstruction/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'ed6723c80f0d694cf670e2919b7321b4742b81340cde827783ba9760cf45b3c8'},
 {'path': 'skills/ship/frontend-design/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '0bf4156e15de358351d8964a85cf38a67b518d79f678bd2cce41a2fbd4495450'},
 {'path': 'skills/ship/handoff/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '84c997d9036483928ab0af669b3837b3effcd6c33bdd27354baf5bb6c1571eb0'},
 {'path': 'skills/ship/post-deploy-check/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '1c6219db3c8cad207cb73c2bfc6ba3d5f533daff70ea64504edf70f8bb597bea'},
 {'path': 'skills/ship/prototype/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '1f3425ca3438c7215d80a1da7a06ebd67da62d0b60afb8fe0a862f1eea87422b'},
 {'path': 'skills/ship/research/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '8d5010b11fb312123b4c7101cb141ce4f491b341138a8c4cd7f91fe99a4bf0c8'},
 {'path': 'skills/ship/retro/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'a43e5479151e1e05f35851c49b9e8eb3a9dca588f337511c988be5bec588b1d1'},
 {'path': 'skills/ship/ship-report/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '9627b7ab729a2fbc4615526cb419a2c49a0e08529e32a5a68b7981dda6dc0651'},
 {'path': 'skills/ship/teach/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'cc9095eb5cbc2d6ac943318501e3a35037577616a9361c14c183be400f34ffe2'},
 {'path': 'skills/utils/migrate-to-shoehorn/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'd3309f27b91d1d8819165df30231499a481c2b36722fc9a7fe4d1c450c8f8887'},
 {'path': 'skills/utils/repo-bootstrap/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'f23264994ee42ce507b32b287d2045a4b1ee9061f9927651fbfe9b54c99877d0'},
 {'path': 'skills/utils/scaffold-exercises/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '86b0f92d683d2c8c205b24e3ff4540e163d478f251bab0eaf75e87c093b06df4'},
 {'path': 'skills/utils/setup-matt-pocock-skills/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'b75aa168109208d4fa603596baf05f59061d7cb1318ec7060dd0f625dfd6ef73'},
 {'path': 'skills/utils/wait-what/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '762e6213f1e985e23ea9dbe0724662541b55c2fb9a9f5a716711f1da06be8885'},
 {'path': 'skills/utils/wizard/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '2bf24290c64aada0732e6c04cb3d920437dcbfe45184f7b3fe27a64597f14225'},
 {'path': 'skills/utils/writing-for-agents/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '4eb332441e49c1daae380efdcd938e8777bea7b2eefabe8e78fa71f833373735'},
 {'path': 'skills/ux-review/SKILL.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': 'f309be9c309cf5ca816d1bafe65c4bb13af8e91f8922638f64959aa007665914'},
 {'path': 'skills/ux-review/references/rules.md',
  'operation': 'modify',
  'class': 'skills',
  'before_sha256': '86360cabff2457f170bc4c38d3a6c69859425f817f36e425c701b9e9455d19b6'},
 {'path': 'runtime/session-size-docker/guard.py',
  'operation': 'modify',
  'class': 'guard_diagnostics_only',
  'before_sha256': '0cf352a05c39129d691c2a4dfc99e15e157e11a5b0f2fbaef632daa49be6f41f'},
 {'path': 'provenance/source-map.json',
  'operation': 'modify',
  'class': 'derived_metadata',
  'before_sha256': 'ab7c5c24e99f1f0607523945415b850e00de636b37165679bcbce582ffe14db5'},
 {'path': 'provenance/layout-migration.json',
  'operation': 'modify',
  'class': 'derived_metadata',
  'before_sha256': 'ca34180a94f6cf279096ce7f21fc62415a23f679517e5c7e3d1a0b495b1629e2'},
 {'path': 'provenance/authorized-additions.json',
  'operation': 'modify',
  'class': 'derived_metadata',
  'before_sha256': '9075e63ee22e8a4668d7e6e372448caeed818f853c5a08741ea1f10d772e182f'},
 {'path': 'release-manifest.json',
  'operation': 'modify',
  'class': 'derived_metadata',
  'before_sha256': '4d766b7ce83e730a1cbd767b5ddae1c8c2b2c08d8330564e87747b372248b4f4'},
 {'path': 'checksums.sha256',
  'operation': 'modify',
  'class': 'derived_metadata',
  'before_sha256': 'a8f76ecf3adcdd79b65a9cdef71c56b4e57396b3afcdbbb882833650ce69b5d3'},
 {'path': 'docs/translations/en/ai-factory/history.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'ai-factory/history.md',
  'original_sha256': 'd7520cdbe02175d651383dbe6c1e2ab756fa584357e096b5b42b279a0b752cdf'},
 {'path': 'docs/translations/en/ai-factory/repo-evidence.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'ai-factory/repo-evidence.md',
  'original_sha256': '1dc7347146630f15d4b0fff6a3878b21f0787006494be0d26c96a49f3585116c'},
 {'path': 'docs/translations/en/docs/legacy/starter-readme.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'docs/legacy/starter-readme.md',
  'original_sha256': '6329060b1357c88ca744fb691a44dc28912b85a941b0c1507fbccb7154a8c7b4'},
 {'path': 'docs/translations/en/docs/guides/obsidian-cheatsheet.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'docs/guides/obsidian-cheatsheet.md',
  'original_sha256': 'c1a2eadb8611250b0bcaeac2fffa8f0cd0396fa4852af2f1886413e5e359ffc0'},
 {'path': 'docs/translations/en/docs/guides/skills-cheatsheet.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'docs/guides/skills-cheatsheet.md',
  'original_sha256': '4aa1bcca3b8c263499afadeb266ba06eda066e2cd0492643973ab8b6dece0bdd'},
 {'path': 'docs/translations/en/rules/agent-stream-to-file.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'rules/agent-stream-to-file.md',
  'original_sha256': '4b35270e78dc9bfdf2ff849cfeca28266649e40dc380c0e2ef2aaa0c6110a7e0'},
 {'path': 'docs/translations/en/rules/multi-model-roles.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'rules/multi-model-roles.md',
  'original_sha256': '908d20088fcc0c49a1316ee43e92d671448f2c9336ef287103b2df3cdc2a371f'},
 {'path': 'docs/translations/en/rules/repo-standards-manifest.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'rules/repo-standards-manifest.md',
  'original_sha256': 'fe4c59fa3705145be5d197e031a301274a0c00d1ad5d8d64cbba3c19d6b87b82'},
 {'path': 'docs/translations/en/rules/typescript-pocock-idioms.md',
  'operation': 'create',
  'class': 'historical_translation',
  'original': 'rules/typescript-pocock-idioms.md',
  'original_sha256': '06b659fe1b25ea31bd57b093b48646270ac08b05320798be4f50c94884266c42'},
 {'path': 'provenance/english-translations.json',
  'operation': 'create',
  'class': 'translation_contract_or_test'},
 {'path': 'tools/verify_translation.py',
  'operation': 'create',
  'class': 'translation_contract_or_test'},
 {'path': 'tests/collection/test_english_translation.py',
  'operation': 'create',
  'class': 'translation_contract_or_test'}]
# Exact accepted local-project cleanup, seal 37569ea6af4bc15de3c3ddc4767797f57673fcb5a4bf390bfbc80e18cf52dfe4.
# These fixed source-bound operations are not read from mutable provenance.
# Reversal restores the reviewed English candidate for all existing baseline checks;
# exact candidate hashes additionally bind narrative, labels and banner truth.
ALLOWLIST.extend([{'path': 'ai-factory/repo-evidence.md',
  'operation': 'modify',
  'class': 'historical_cleanup_only',
  'before_sha256': '1dc7347146630f15d4b0fff6a3878b21f0787006494be0d26c96a49f3585116c'},
 {'path': 'docs/guides/obsidian-cheatsheet.md',
  'operation': 'modify',
  'class': 'historical_cleanup_only',
  'before_sha256': 'c1a2eadb8611250b0bcaeac2fffa8f0cd0396fa4852af2f1886413e5e359ffc0'},
 {'path': 'provenance/link-exceptions.json',
  'operation': 'modify',
  'class': 'derived_metadata',
  'before_sha256': '5d3b6a2dc1b00bf3b5073ed7abde7c926a6bb2bc22c1aa59d049842c900d42eb'}])
CLEANUP_FILES = {'ai-factory/crg.md': {'path': 'ai-factory/crg.md',
                       'before_sha256': 'f310e3f1d73f44311932bfd9d66d972d2e153a4d4f59595a9e204af88ce53dbe',
                       'proposed_sha256': 'c09092aa902e551906f79e085c9cacb9ff1995439b65bf44da508b88cffdfb0c',
                       'removed_clickable_occurrences': 0,
                       'hunks': [{'start': 9372, 'end': 9376, 'before': 'R', 'after': 'Hist'},
                                 {'start': 9377, 'end': 9388, 'before': '', 'after': 'rical check'},
                                 {'start': 9389, 'end': 9390, 'before': '', 'after': 'u'},
                                 {'start': 9393, 'end': 9393, 'before': '~/projects/cargo/', 'after': ''},
                                 {'start': 9407, 'end': 9428, 'before': '', 'after': ' (local root omitted)'}],
                       'historical_original': False},
 'ai-factory/feature-lifecycle.md': {'path': 'ai-factory/feature-lifecycle.md',
                                     'before_sha256': '71d3d4acc70ac0479a3b7a19dca57f3f679bcb4126dd50db079ac204a7b770ea',
                                     'proposed_sha256': '35ce2cc6bc16d95c27f20296209bf3a395717e2d803ba71674c9d34c5021673e',
                                     'removed_clickable_occurrences': 6,
                                     'hunks': [{'start': 19838, 'end': 19838, 'before': '[', 'after': ''},
                                               {'start': 19849,
                                                'end': 19849,
                                                'before': '](~/projects/cassiopeia/cassiopeia-admin-ui/work/README.md)',
                                                'after': ''},
                                               {'start': 20142,
                                                'end': 20143,
                                                'before': '[task-workflow](~/projects/cargo/cargotrans-ui/',
                                                'after': '`'},
                                               {'start': 20170, 'end': 20171, 'before': ')', 'after': '`'},
                                               {'start': 20232, 'end': 20232, 'before': '[', 'after': ''},
                                               {'start': 20244, 'end': 20245, 'before': ']', 'after': ' '},
                                               {'start': 20246,
                                                'end': 20247,
                                                'before': '~/projects/cargo/cargotrans-ui/',
                                                'after': '`'},
                                               {'start': 20277, 'end': 20278, 'before': '', 'after': '`'},
                                               {'start': 20406, 'end': 20406, 'before': '[', 'after': ''},
                                               {'start': 20419, 'end': 20420, 'before': ']', 'after': ' '},
                                               {'start': 20421,
                                                'end': 20422,
                                                'before': '~/projects/cargo/cargotrans-ui/',
                                                'after': '`'},
                                               {'start': 20439, 'end': 20440, 'before': '', 'after': '`'},
                                               {'start': 20551, 'end': 20551, 'before': '[', 'after': ''},
                                               {'start': 20564,
                                                'end': 20564,
                                                'before': '](~/projects/courses/work/tasks.md)',
                                                'after': ''},
                                               {'start': 20849, 'end': 20849, 'before': '[', 'after': ''},
                                               {'start': 20857,
                                                'end': 20857,
                                                'before': '](~/projects/courses/Makefile)',
                                                'after': ''}],
                                     'historical_original': False},
 'ai-factory/repo-evidence.md': {'path': 'ai-factory/repo-evidence.md',
                                 'before_sha256': '1dc7347146630f15d4b0fff6a3878b21f0787006494be0d26c96a49f3585116c',
                                 'proposed_sha256': '66f21a694d2043e3aee1e4b10e216ab5b0251517f58fb355fa8fb5368e0e1bbe',
                                 'removed_clickable_occurrences': 28,
                                 'hunks': [{'start': 501,
                                            'end': 501,
                                            'before': '~/projects/b2bsoft/genericui/',
                                            'after': ''},
                                           {'start': 583, 'end': 583, 'before': '[', 'after': ''},
                                           {'start': 594,
                                            'end': 594,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/README.md)',
                                            'after': ''},
                                           {'start': 598, 'end': 598, 'before': '[', 'after': ''},
                                           {'start': 609,
                                            'end': 609,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/AGENTS.md)',
                                            'after': ''},
                                           {'start': 630,
                                            'end': 630,
                                            'before': '~/projects/b2bsoft/genericui/',
                                            'after': ''},
                                           {'start': 1243, 'end': 1243, 'before': '[', 'after': ''},
                                           {'start': 1259,
                                            'end': 1259,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/PRINCIPLES.md)',
                                            'after': ''},
                                           {'start': 1272, 'end': 1272, 'before': '[', 'after': ''},
                                           {'start': 1290,
                                            'end': 1290,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/specs/constitution.md)',
                                            'after': ''},
                                           {'start': 1542, 'end': 1542, 'before': '[', 'after': ''},
                                           {'start': 1552,
                                            'end': 1552,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/lib/chat/docs/adr/0026-citation-replay-fold-is-a-cross-repo-contract.md)',
                                            'after': ''},
                                           {'start': 1686, 'end': 1686, 'before': '[', 'after': ''},
                                           {'start': 1696,
                                            'end': 1696,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/lib/chat/docs/adr/0032-rewind-surviving-events.md)',
                                            'after': ''},
                                           {'start': 1950, 'end': 1950, 'before': '[', 'after': ''},
                                           {'start': 1969,
                                            'end': 1969,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/specs/constitution.md)',
                                            'after': ''},
                                           {'start': 2416, 'end': 2416, 'before': '[', 'after': ''},
                                           {'start': 2433,
                                            'end': 2433,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/PRINCIPLES.md)',
                                            'after': ''},
                                           {'start': 4247, 'end': 4247, 'before': '[', 'after': ''},
                                           {'start': 4263,
                                            'end': 4263,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/work/README.md)',
                                            'after': ''},
                                           {'start': 4265, 'end': 4265, 'before': '[', 'after': ''},
                                           {'start': 4284,
                                            'end': 4284,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/.claude/agents/work-reviewer.md)',
                                            'after': ''},
                                           {'start': 4286, 'end': 4286, 'before': '[', 'after': ''},
                                           {'start': 4305,
                                            'end': 4305,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/docs/design/README.md)',
                                            'after': ''},
                                           {'start': 4307, 'end': 4307, 'before': '[', 'after': ''},
                                           {'start': 4323,
                                            'end': 4323,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/docs/adr-format.md)',
                                            'after': ''},
                                           {'start': 4336, 'end': 4336, 'before': '[', 'after': ''},
                                           {'start': 4352,
                                            'end': 4352,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/work/README.md)',
                                            'after': ''},
                                           {'start': 4874, 'end': 4874, 'before': '[', 'after': ''},
                                           {'start': 4904,
                                            'end': 4904,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/.claude/skills/work/SKILL.md)',
                                            'after': ''},
                                           {'start': 5772, 'end': 5772, 'before': '[', 'after': ''},
                                           {'start': 5789,
                                            'end': 5789,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/work/README.md)',
                                            'after': ''},
                                           {'start': 5978, 'end': 5978, 'before': '[', 'after': ''},
                                           {'start': 5996,
                                            'end': 5996,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/specs/README.md)',
                                            'after': ''},
                                           {'start': 6001, 'end': 6001, 'before': '[', 'after': ''},
                                           {'start': 6017,
                                            'end': 6017,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/specs/prompts/validate-spec.md)',
                                            'after': ''},
                                           {'start': 6051, 'end': 6051, 'before': '[', 'after': ''},
                                           {'start': 6067,
                                            'end': 6067,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/specs/prompts/analyze-specs.md)',
                                            'after': ''},
                                           {'start': 6210, 'end': 6210, 'before': '[', 'after': ''},
                                           {'start': 6226,
                                            'end': 6226,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/specs/prompts/pre-qa-review.md)',
                                            'after': ''},
                                           {'start': 6647, 'end': 6647, 'before': '[', 'after': ''},
                                           {'start': 6682,
                                            'end': 6682,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/plan.md)',
                                            'after': ''},
                                           {'start': 6771, 'end': 6771, 'before': '[', 'after': ''},
                                           {'start': 6784,
                                            'end': 6784,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md)',
                                            'after': ''},
                                           {'start': 6834, 'end': 6834, 'before': '[', 'after': ''},
                                           {'start': 6850,
                                            'end': 6850,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md)',
                                            'after': ''},
                                           {'start': 7022, 'end': 7022, 'before': '[', 'after': ''},
                                           {'start': 7056,
                                            'end': 7056,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/work/002-keda-scaling/review.md)',
                                            'after': ''},
                                           {'start': 7159, 'end': 7159, 'before': '[', 'after': ''},
                                           {'start': 7202,
                                            'end': 7202,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/work/003-jobs-heartbeat-research/plan.md)',
                                            'after': ''},
                                           {'start': 7374, 'end': 7374, 'before': '[', 'after': ''},
                                           {'start': 7418,
                                            'end': 7418,
                                            'before': '](../../projects/b2bsoft/genericui/generic-ui/work/004-navigate-message-feedback/plan.md)',
                                            'after': ''},
                                           {'start': 7770, 'end': 7770, 'before': '[', 'after': ''},
                                           {'start': 7786,
                                            'end': 7786,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/docs/adr-format.md)',
                                            'after': ''},
                                           {'start': 8141, 'end': 8141, 'before': '[', 'after': ''},
                                           {'start': 8152,
                                            'end': 8152,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md)',
                                            'after': ''},
                                           {'start': 8218, 'end': 8218, 'before': '[', 'after': ''},
                                           {'start': 8229,
                                            'end': 8229,
                                            'before': '](../../projects/b2bsoft/genericui/openai-qna/.claude/skills/work/SKILL.md)',
                                            'after': ''}],
                                 'historical_original': True},
 'ai-factory/roadmap.md': {'path': 'ai-factory/roadmap.md',
                           'before_sha256': '3fc1b3134fa9341c189ca1c634024f0970b71903a92b0144573decf6cf0f342c',
                           'proposed_sha256': '72f690b0a4b3a0eb7c7d4d4f24680d1dde8207137cab83784160d1b7e8e1495d',
                           'removed_clickable_occurrences': 0,
                           'hunks': [{'start': 4562, 'end': 4575, 'before': '`', 'after': 'From the sele'},
                                     {'start': 4576, 'end': 4578, 'before': '', 'after': 'te'},
                                     {'start': 4580, 'end': 4583, 'before': '~/', 'after': 'dg '},
                                     {'start': 4590, 'end': 4590, 'before': 's/dg', 'after': ''},
                                     {'start': 4591, 'end': 4596, 'before': '&&', 'after': 'root:'},
                                     {'start': 4597, 'end': 4598, 'before': '', 'after': '`'}],
                           'historical_original': False},
 'ai-factory/status.md': {'path': 'ai-factory/status.md',
                          'before_sha256': '2e5f7e9ae6012b7e4f9bc265654d24957d19ad579e0b4e718fb2d1256ca781f6',
                          'proposed_sha256': '704bf0fcf929b6ea9cb031dadcf65ee6e6a293fd2befedd09e41863462a2fe8d',
                          'removed_clickable_occurrences': 1,
                          'hunks': [{'start': 7434, 'end': 7434, 'before': '[', 'after': ''},
                                    {'start': 7447,
                                     'end': 7447,
                                     'before': '](../../projects/b2bsoft/genericui/openai-qna/.claude/skills/work/SKILL.md)',
                                     'after': ''}],
                          'historical_original': False},
 'docs/guides/obsidian-cheatsheet.md': {'path': 'docs/guides/obsidian-cheatsheet.md',
                                        'before_sha256': 'c1a2eadb8611250b0bcaeac2fffa8f0cd0396fa4852af2f1886413e5e359ffc0',
                                        'proposed_sha256': 'e653eb2119b93dd4a7a4b686111d8b2a570c3d17ea29d683989a7b76e6688977',
                                        'removed_clickable_occurrences': 0,
                                        'hunks': [{'start': 3453,
                                                   'end': 3453,
                                                   'before': '~/projects/',
                                                   'after': ''},
                                                  {'start': 3463, 'end': 3463, 'before': '/…', 'after': ''},
                                                  {'start': 3506,
                                                   'end': 3506,
                                                   'before': '~/projects/cargo/',
                                                   'after': ''},
                                                  {'start': 3560,
                                                   'end': 3560,
                                                   'before': '~/projects/',
                                                   'after': ''}],
                                        'historical_original': True},
 'docs/translations/en/ai-factory/repo-evidence.md': {'path': 'docs/translations/en/ai-factory/repo-evidence.md',
                                                      'before_sha256': '2bcd52b9f53f601bacd4c009d96410682ea4af2fa3976d77f0fb0d6438641d63',
                                                      'proposed_sha256': '1ddebf9c43144e99b3c97f686f41436e1b12ae573f2b0782b9d9237b952a1971',
                                                      'removed_clickable_occurrences': 28,
                                                      'hunks': [{'start': 372,
                                                                 'end': 379,
                                                                 'before': '',
                                                                 'after': 'sealed '},
                                                                {'start': 388,
                                                                 'end': 392,
                                                                 'before': '',
                                                                 'after': 'rema'},
                                                                {'start': 393,
                                                                 'end': 394,
                                                                 'before': '',
                                                                 'after': 'n'},
                                                                {'start': 405,
                                                                 'end': 502,
                                                                 'before': '',
                                                                 'after': '; the in-repository historical '
                                                                          'document has a separately recorded '
                                                                          'local-project reference cleanup'},
                                                                {'start': 1350,
                                                                 'end': 1521,
                                                                 'before': '',
                                                                 'after': '. Source names and line numbers below '
                                                                          'are historical attributions; '
                                                                          'unavailable local-project link targets '
                                                                          'have been removed without claiming '
                                                                          'current access or revalidation'},
                                                                {'start': 1544,
                                                                 'end': 1544,
                                                                 'before': '~/projects/b2bsoft/genericui/',
                                                                 'after': ''},
                                                                {'start': 1634,
                                                                 'end': 1634,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 1645,
                                                                 'end': 1645,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/README.md)',
                                                                 'after': ''},
                                                                {'start': 1650,
                                                                 'end': 1650,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 1661,
                                                                 'end': 1661,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/AGENTS.md)',
                                                                 'after': ''},
                                                                {'start': 1682,
                                                                 'end': 1682,
                                                                 'before': '~/projects/b2bsoft/genericui/',
                                                                 'after': ''},
                                                                {'start': 2411,
                                                                 'end': 2411,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 2427,
                                                                 'end': 2427,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/PRINCIPLES.md)',
                                                                 'after': ''},
                                                                {'start': 2440,
                                                                 'end': 2440,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 2458,
                                                                 'end': 2458,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/specs/constitution.md)',
                                                                 'after': ''},
                                                                {'start': 2751,
                                                                 'end': 2751,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 2761,
                                                                 'end': 2761,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/lib/chat/docs/adr/0026-citation-replay-fold-is-a-cross-repo-contract.md)',
                                                                 'after': ''},
                                                                {'start': 2899,
                                                                 'end': 2899,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 2909,
                                                                 'end': 2909,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/lib/chat/docs/adr/0032-rewind-surviving-events.md)',
                                                                 'after': ''},
                                                                {'start': 3185,
                                                                 'end': 3185,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 3204,
                                                                 'end': 3204,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/specs/constitution.md)',
                                                                 'after': ''},
                                                                {'start': 3638,
                                                                 'end': 3638,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 3655,
                                                                 'end': 3655,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/PRINCIPLES.md)',
                                                                 'after': ''},
                                                                {'start': 5629,
                                                                 'end': 5629,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 5645,
                                                                 'end': 5645,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/work/README.md)',
                                                                 'after': ''},
                                                                {'start': 5647,
                                                                 'end': 5647,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 5666,
                                                                 'end': 5666,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/.claude/agents/work-reviewer.md)',
                                                                 'after': ''},
                                                                {'start': 5668,
                                                                 'end': 5668,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 5687,
                                                                 'end': 5687,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/docs/design/README.md)',
                                                                 'after': ''},
                                                                {'start': 5689,
                                                                 'end': 5689,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 5705,
                                                                 'end': 5705,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/docs/adr-format.md)',
                                                                 'after': ''},
                                                                {'start': 5718,
                                                                 'end': 5718,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 5734,
                                                                 'end': 5734,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/work/README.md)',
                                                                 'after': ''},
                                                                {'start': 6336,
                                                                 'end': 6336,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 6366,
                                                                 'end': 6366,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/.claude/skills/work/SKILL.md)',
                                                                 'after': ''},
                                                                {'start': 7300,
                                                                 'end': 7300,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 7317,
                                                                 'end': 7317,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/work/README.md)',
                                                                 'after': ''},
                                                                {'start': 7520,
                                                                 'end': 7520,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 7538,
                                                                 'end': 7538,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/specs/README.md)',
                                                                 'after': ''},
                                                                {'start': 7543,
                                                                 'end': 7543,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 7559,
                                                                 'end': 7559,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/specs/prompts/validate-spec.md)',
                                                                 'after': ''},
                                                                {'start': 7592,
                                                                 'end': 7592,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 7608,
                                                                 'end': 7608,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/specs/prompts/analyze-specs.md)',
                                                                 'after': ''},
                                                                {'start': 7761,
                                                                 'end': 7761,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 7777,
                                                                 'end': 7777,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/specs/prompts/pre-qa-review.md)',
                                                                 'after': ''},
                                                                {'start': 8258,
                                                                 'end': 8258,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 8293,
                                                                 'end': 8293,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/plan.md)',
                                                                 'after': ''},
                                                                {'start': 8402,
                                                                 'end': 8402,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 8415,
                                                                 'end': 8415,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md)',
                                                                 'after': ''},
                                                                {'start': 8469,
                                                                 'end': 8469,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 8485,
                                                                 'end': 8485,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md)',
                                                                 'after': ''},
                                                                {'start': 8652,
                                                                 'end': 8652,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 8686,
                                                                 'end': 8686,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/work/002-keda-scaling/review.md)',
                                                                 'after': ''},
                                                                {'start': 8805,
                                                                 'end': 8805,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 8848,
                                                                 'end': 8848,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/work/003-jobs-heartbeat-research/plan.md)',
                                                                 'after': ''},
                                                                {'start': 9051,
                                                                 'end': 9051,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 9095,
                                                                 'end': 9095,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/generic-ui/work/004-navigate-message-feedback/plan.md)',
                                                                 'after': ''},
                                                                {'start': 9494,
                                                                 'end': 9494,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 9510,
                                                                 'end': 9510,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/docs/adr-format.md)',
                                                                 'after': ''},
                                                                {'start': 9890,
                                                                 'end': 9890,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 9901,
                                                                 'end': 9901,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md)',
                                                                 'after': ''},
                                                                {'start': 9973,
                                                                 'end': 9973,
                                                                 'before': '[',
                                                                 'after': ''},
                                                                {'start': 9984,
                                                                 'end': 9984,
                                                                 'before': '](../../../../../projects/b2bsoft/genericui/openai-qna/.claude/skills/work/SKILL.md)',
                                                                 'after': ''}],
                                                      'historical_original': False},
 'docs/translations/en/docs/guides/obsidian-cheatsheet.md': {'path': 'docs/translations/en/docs/guides/obsidian-cheatsheet.md',
                                                             'before_sha256': 'fc0af8ba5bcaf27c9221a9ffc14a65934fc19d26c63250a22b13f76ca3a6f18a',
                                                             'proposed_sha256': '663bcff5e0b9cc0a458d0173caa4c7ab35900fd0993db3ca7f62f9977f459f0c',
                                                             'removed_clickable_occurrences': 0,
                                                             'hunks': [{'start': 453,
                                                                        'end': 460,
                                                                        'before': '',
                                                                        'after': 'sealed '},
                                                                       {'start': 469,
                                                                        'end': 473,
                                                                        'before': '',
                                                                        'after': 'rema'},
                                                                       {'start': 474,
                                                                        'end': 475,
                                                                        'before': '',
                                                                        'after': 'n'},
                                                                       {'start': 486,
                                                                        'end': 583,
                                                                        'before': '',
                                                                        'after': '; the in-repository historical '
                                                                                 'document has a separately '
                                                                                 'recorded local-project '
                                                                                 'reference cleanup'},
                                                                       {'start': 4608,
                                                                        'end': 4608,
                                                                        'before': '~/projects/',
                                                                        'after': ''},
                                                                       {'start': 4618,
                                                                        'end': 4618,
                                                                        'before': '/…',
                                                                        'after': ''},
                                                                       {'start': 4661,
                                                                        'end': 4661,
                                                                        'before': '~/projects/cargo/',
                                                                        'after': ''},
                                                                       {'start': 4715,
                                                                        'end': 4715,
                                                                        'before': '~/projects/',
                                                                        'after': ''}],
                                                             'historical_original': False},
 'skills/entity-e2e-coverage/references/testing-rules.md': {'path': 'skills/entity-e2e-coverage/references/testing-rules.md',
                                                            'before_sha256': '806b1e6dcb4464aad228ccd105707437a81354c6ec678220e7c56ef1ee81afe7',
                                                            'proposed_sha256': 'b3005971178abeb238edcd9c56b275f586ca05b2894a9c4f610667a30d7762c0',
                                                            'removed_clickable_occurrences': 10,
                                                            'hunks': [{'start': 2124,
                                                                       'end': 2124,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 2138,
                                                                       'end': 2138,
                                                                       'before': '](~/projects/cargo/cargotrans-ui/docs/adr/0008-a-wait-must-watch-the-thing-that-varies.md)',
                                                                       'after': ''},
                                                                      {'start': 5707,
                                                                       'end': 5707,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 5740,
                                                                       'end': 5740,
                                                                       'before': '](~/projects/cassiopeia/cassiopeia-admin-ui/docs/agent/22-testing-strategy.md)',
                                                                       'after': ''},
                                                                      {'start': 5919,
                                                                       'end': 5919,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 5927,
                                                                       'end': 5927,
                                                                       'before': '](~/projects/cassiopeia/cassiopeia-admin-ui/docs/adr/0071-e2e-shared-session-and-new-spec-construction-rules.md)',
                                                                       'after': ''},
                                                                      {'start': 6144,
                                                                       'end': 6144,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 6158,
                                                                       'end': 6158,
                                                                       'before': '](~/projects/cassiopeia/cassiopeia-admin-ui/work/README.md)',
                                                                       'after': ''},
                                                                      {'start': 6738,
                                                                       'end': 6738,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 6746,
                                                                       'end': 6746,
                                                                       'before': '](~/projects/cargo/cargotrans-ui/docs/adr/0008-a-wait-must-watch-the-thing-that-varies.md)',
                                                                       'after': ''},
                                                                      {'start': 6957,
                                                                       'end': 6957,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 6965,
                                                                       'end': 6965,
                                                                       'before': '](~/projects/cargo/cargotrans-ui/docs/adr/0014-running-tests-gates-stands-live-telemetry.md)',
                                                                       'after': ''},
                                                                      {'start': 7307,
                                                                       'end': 7307,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 7324,
                                                                       'end': 7324,
                                                                       'before': '](~/projects/cargo/cargotrans-ui/tests/FIXTURES.md)',
                                                                       'after': ''},
                                                                      {'start': 7566,
                                                                       'end': 7566,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 7583,
                                                                       'end': 7583,
                                                                       'before': '](~/projects/cargo/cargotrans-ui/work/qa/README.md)',
                                                                       'after': ''},
                                                                      {'start': 7673,
                                                                       'end': 7673,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 7700,
                                                                       'end': 7700,
                                                                       'before': '](~/projects/courses/docs/development/testing.md)',
                                                                       'after': ''},
                                                                      {'start': 8039,
                                                                       'end': 8039,
                                                                       'before': '[',
                                                                       'after': ''},
                                                                      {'start': 8047,
                                                                       'end': 8047,
                                                                       'before': '](~/projects/courses/Makefile)',
                                                                       'after': ''}],
                                                            'historical_original': False}}
CLEANUP_METADATA = {'provenance/link-exceptions.json': {'key': 'references',
                                     'before_records_sha256': '33a99d3bb10016e7600f7c61b13f4dfad91d70ac22efd5fd99c5c29a68ceb8ce',
                                     'after_records_sha256': '87d06ca44aa41d3cd5408b522982fe54cedf1369e1651b07500f812f451a553c',
                                     'removed_records_sha256': 'a1b9019c8496d94ad7e955e575f10ec56a7f65e51177df091f33c1f5c149a312',
                                     'removed_records': 45,
                                     'retained_records': 18,
                                     'before_sha256': '5d3b6a2dc1b00bf3b5073ed7abde7c926a6bb2bc22c1aa59d049842c900d42eb',
                                     'proposed_sha256': '4106fa04ffb7c831b24d825585218780ea83bbfa500bdb60f0cae058d1e4b810'},
 'provenance/source-map.json': {'key': 'links',
                                'before_records_sha256': '894fae88f16e7b9cc063ddcd5ab91fd22884faddc46f337f0397dc36b1e15967',
                                'after_records_sha256': 'fb4c23e1e983934742352189ebd8821830104132a806292536336615b41845b3',
                                'removed_records_sha256': '4b508f2bbf369097c9eda083e89b5341a08f783b84cf921d5b982965e37aaa5c',
                                'removed_records': 45,
                                'retained_records': 292}}

DESCRIPTION_PATHS = ['skills/arch/caveman/SKILL.md',
 'skills/arch/code-review/SKILL.md',
 'skills/arch/codebase-design/SKILL.md',
 'skills/arch/diagnosing-bugs/SKILL.md',
 'skills/arch/domain-modeling/SKILL.md',
 'skills/arch/improve-codebase-architecture/SKILL.md',
 'skills/arch/receiving-code-review/SKILL.md',
 'skills/arch/tdd/SKILL.md',
 'skills/crg/crg-debug-issue/SKILL.md',
 'skills/crg/crg-explore-codebase/SKILL.md',
 'skills/crg/crg-refactor-safely/SKILL.md',
 'skills/crg/crg-review-changes/SKILL.md',
 'skills/deliver/implement-spec/SKILL.md',
 'skills/deliver/implement/SKILL.md',
 'skills/deliver/to-spec/SKILL.md',
 'skills/deliver/to-tickets/SKILL.md',
 'skills/deliver/triage/SKILL.md',
 'skills/deliver/wayfinder/SKILL.md',
 'skills/git/git-guardrails-claude-code/SKILL.md',
 'skills/git/pr/SKILL.md',
 'skills/git/resolving-merge-conflicts/SKILL.md',
 'skills/git/setup-pre-commit/SKILL.md',
 'skills/plan/ask-matt/SKILL.md',
 'skills/plan/grill-me/SKILL.md',
 'skills/plan/grill-with-docs/SKILL.md',
 'skills/plan/grilling/SKILL.md',
 'skills/plan/to-questionnaire/SKILL.md',
 'skills/pt/ponytail-audit/SKILL.md',
 'skills/pt/ponytail-debt/SKILL.md',
 'skills/pt/ponytail-gain/SKILL.md',
 'skills/pt/ponytail-review/SKILL.md',
 'skills/pt/ponytail/SKILL.md',
 'skills/reference-ui-reconstruction/SKILL.md',
 'skills/ship/frontend-design/SKILL.md',
 'skills/ship/handoff/SKILL.md',
 'skills/ship/prototype/SKILL.md',
 'skills/ship/research/SKILL.md',
 'skills/ship/retro/SKILL.md',
 'skills/ship/teach/SKILL.md',
 'skills/utils/migrate-to-shoehorn/SKILL.md',
 'skills/utils/scaffold-exercises/SKILL.md',
 'skills/utils/setup-matt-pocock-skills/SKILL.md',
 'skills/utils/wait-what/SKILL.md',
 'skills/utils/wizard/SKILL.md',
 'skills/utils/writing-for-agents/SKILL.md']
GUARD_TARGETS = [{'line': 382,
  'original': 'CHECKPOINT_CLAIMED_BY_OTHER: цей checkpoint уже належить іншій сесії. Звірити exact '
              'ID чи обрати інший? Не переносити claim і не продовжувати автоматично.',
  'preserved_prefix': 'CHECKPOINT_CLAIMED_BY_OTHER:'},
 {'line': 383,
  'original': 'CLAIM_STATE_MISMATCH: claim і session state не узгоджені; потрібна ручна звірка '
              'exact checkpoint. Не очищати markers.',
  'preserved_prefix': 'CLAIM_STATE_MISMATCH:'},
 {'line': 384,
  'original': 'INVALID_CHECKPOINT_ID: потрібен explicit checkpoint ID; не обирати latest.',
  'preserved_prefix': 'INVALID_CHECKPOINT_ID:'},
 {'line': 385,
  'original': 'MISSING_HOST_SESSION: hook payload не містить чинної host/session identity.',
  'preserved_prefix': 'MISSING_HOST_SESSION:'},
 {'line': 386,
  'original': 'INCOMPLETE_CHECKPOINT: потрібен завершений exact checkpoint.',
  'preserved_prefix': 'INCOMPLETE_CHECKPOINT:'},
 {'line': 387,
  'original': 'CHECKPOINT_TIME_INVALID: час checkpoint поза дозволеним вікном; потрібна ручна '
              'звірка.',
  'preserved_prefix': 'CHECKPOINT_TIME_INVALID:'},
 {'line': 388,
  'original': 'SNAPSHOT_MISMATCH: root/branch/HEAD/dirty змінились; звірити exact checkpoint, без '
              'автоматичного продовження.',
  'preserved_prefix': 'SNAPSHOT_MISMATCH:'},
 {'line': 389,
  'original': 'SOURCE_SESSION_REFUSED: source session не може спожити власний checkpoint.',
  'preserved_prefix': 'SOURCE_SESSION_REFUSED:'},
 {'line': 390,
  'original': 'CHAIN_LIMIT: потрібна ручна звірка; не скидати depth.',
  'preserved_prefix': 'CHAIN_LIMIT:'},
 {'line': 391,
  'original': 'STATE_UNAVAILABLE: exact state відсутній або завеликий.',
  'preserved_prefix': 'STATE_UNAVAILABLE:'},
 {'line': 392,
  'original': 'UNSAFE_STATE_PATH: symlink state path заборонено.',
  'preserved_prefix': 'UNSAFE_STATE_PATH:'},
 {'line': 393,
  'original': 'STATE_PERMISSIONS: store має бути приватним і належати поточному користувачу.',
  'preserved_prefix': 'STATE_PERMISSIONS:'},
 {'line': 394,
  'original': 'PAYLOAD_TOO_LARGE: потрібен ручний checkpoint.',
  'preserved_prefix': 'PAYLOAD_TOO_LARGE:'},
 {'line': 397,
  'original': 'SNAPSHOT_CHECK_FAILED: перевірка repository snapshot не завершилась. ',
  'preserved_prefix': 'SNAPSHOT_CHECK_FAILED:'},
 {'line': 399,
  'original': 'MALFORMED_JSON: hook payload або exact state має невалідний JSON; звірити формат '
              'без виведення вмісту.',
  'preserved_prefix': 'MALFORMED_JSON:'},
 {'line': 401,
  'original': 'INVALID_HANDOFF_DATA: validation відхилила payload/state; звірити exact ID і '
              'metadata без виведення приватного вмісту.',
  'preserved_prefix': 'INVALID_HANDOFF_DATA:'},
 {'line': 403,
  'original': 'MALFORMED_SCHEMA: у payload/state відсутні або некоректні required fields.',
  'preserved_prefix': 'MALFORMED_SCHEMA:'},
 {'line': 405,
  'original': 'STATE_IO: exact state недоступний; не обходити permissions.',
  'preserved_prefix': 'STATE_IO:'},
 {'line': 407,
  'original': 'SNAPSHOT_CHECK_FAILED: перевірка repository snapshot не завершилась.',
  'preserved_prefix': 'SNAPSHOT_CHECK_FAILED:'}]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(root, name):
    """Reject traversal, symlink components, hardlinks and non-files before reading."""
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError('unsafe relative path')
    p = root
    if root.is_symlink():
        raise ValueError('symlink root')
    for part in rel.parts:
        p = p / part
        if p.is_symlink():
            raise ValueError('symlink component')
    if not p.is_file() or p.stat().st_nlink != 1:
        raise ValueError('missing/nonregular/hardlinked file')
    return p.read_bytes()


def inventory(root):
    names = set()
    for p in root.rglob('*'):
        rel = p.relative_to(root)
        if rel.parts[0] == '.git':
            continue
        if p.is_symlink():
            raise ValueError('symlink in tree')
        if p.is_file():
            names.add(rel.as_posix())
        elif not p.is_dir():
            raise ValueError('nonregular tree member')
    return names


def load_baseline(root):
    raw = regular(root, 'release-manifest.json')
    if digest(raw) != BASE_MANIFEST:
        raise ValueError('baseline manifest identity mismatch')
    manifest = json.loads(raw)
    expected = {'release-manifest.json': digest(raw)}
    for row in manifest['files']:
        name = row['path']
        if name in expected:
            raise ValueError('duplicate baseline path')
        if digest(regular(root, name)) != row['sha256']:
            raise ValueError('baseline payload mismatch: ' + name)
        expected[name] = row['sha256']
    checks = regular(root, 'checksums.sha256').decode()
    canonical = ''.join(expected[n] + '  ' + n + '\n' for n in sorted(expected))
    if checks != canonical:
        raise ValueError('baseline checksum closure mismatch')
    if inventory(root) != set(expected) | {'checksums.sha256'}:
        raise ValueError('baseline inventory mismatch')
    return {n: regular(root, n) for n in set(expected) | {'checksums.sha256'}}


def description_parts(text):
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        raise ValueError('missing frontmatter')
    front, body = text.split('\n---\n', 1)
    match = re.search(r'^description:.*(?:\n[ \t]+.*)*', front, re.M)
    if not match:
        raise ValueError('missing description')
    return front[:match.start()] + '<DESCRIPTION>' + front[match.end():], body


def guard_proof(old, new):
    """Only literal token spans on the nineteen approved source lines may differ."""
    targets = {r['line']: r for r in GUARD_TARGETS}
    old_tree, new_tree = ast.parse(old), ast.parse(new)
    def normalize(tree, source, original):
        lines = source.splitlines(keepends=True)
        found = set()
        replacements = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            row = targets.get(node.lineno)
            if row is None or (original and node.value != row['original']):
                continue
            # Keys on the same line must never be mistaken for translated values.
            if not original and not node.value.startswith(row['preserved_prefix']):
                continue
            if node.lineno in found or node.end_lineno != node.lineno:
                raise ValueError('guard duplicate or multiline literal')
            found.add(node.lineno)
            if original and node.value != row['original']:
                raise ValueError('guard original mismatch')
            if not node.value.startswith(row['preserved_prefix'] + ' '):
                raise ValueError('guard prefix changed')
            if node.value.endswith(' ') != row['original'].endswith(' '):
                raise ValueError('guard trailing separator changed')
            if not original and (CYRILLIC.search(node.value) or node.value == row['preserved_prefix'] + ' '):
                raise ValueError('guard untranslated/empty message')
            line = lines[node.lineno - 1].encode()
            replacements.append((node.lineno - 1, node.col_offset, node.end_col_offset))
            node.value = '<TRANSLATED_DIAGNOSTIC>'
        if found != set(targets):
            raise ValueError('guard target set changed')
        for line_no, start, end in sorted(replacements, reverse=True):
            line = lines[line_no].encode()
            lines[line_no] = (line[:start] + b"'<TRANSLATED_DIAGNOSTIC>'" + line[end:]).decode()
        return ast.dump(tree, include_attributes=False), ''.join(lines)
    if normalize(old_tree, old, True) != normalize(new_tree, new, False):
        raise ValueError('guard behavior or out-of-span source changed')


def slug(text):
    text = re.sub(r'</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*|\s*/?)>', '', text).strip().lower()
    text = re.sub(r'[^\w\- ]', '', text, flags=re.UNICODE)
    return text.replace(' ', '-')


def without_inline_code(text, multiline_only=False):
    """Remove paired same-length backtick runs, including multiline spans.

    Blank lines end the paragraph. Unmatched runs stay literal. Indexing each
    delimiter once avoids repeated scans of adversarial unmatched backticks.
    """
    paragraphs = re.split(r'(\n[ \t]*\n)', text)
    for part, paragraph in enumerate(paragraphs):
        runs = list(re.finditer(r'`+', paragraph))
        following, latest = {}, {}
        for i in range(len(runs)-1, -1, -1):
            length = len(runs[i][0])
            if length in latest:
                following[i] = latest[length]
            latest[length] = i
        pieces, pos, i = [], 0, 0
        while i < len(runs):
            if i not in following:
                i += 1
                continue
            end = following[i]
            pieces.append(paragraph[pos:runs[i].start()])
            span = paragraph[runs[i].start():runs[end].end()]
            pieces.append(span if multiline_only and '\n' not in span else
                          ''.join('\n' if ch == '\n' else ' ' for ch in span))
            pos = runs[end].end()
            i = end + 1
        pieces.append(paragraph[pos:])
        paragraphs[part] = ''.join(pieces)
    return ''.join(paragraphs)


def visible_markdown(text, drop_inline=False):
    """Bounded CommonMark fence/comment scan; no code-example anchor evidence."""
    output, fence, comment = [], None, False
    for line in text.splitlines():
        if fence:
            if re.fullmatch(r' {0,3}' + re.escape(fence[0]) + '{' + str(fence[1]) + r',}\s*', line):
                fence = None
            output.append('')
            continue
        # HTML comments may span lines. Their contents cannot open code fences.
        clean, pos = '', 0
        while pos < len(line):
            if comment:
                end = line.find('-->', pos)
                if end < 0:
                    pos = len(line)
                else:
                    comment = False; pos = end + 3
            else:
                begin = line.find('<!--', pos)
                if begin < 0:
                    clean += line[pos:]; pos = len(line)
                else:
                    clean += line[pos:begin]; comment = True; pos = begin + 4
        opening = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', clean)
        if opening and not (opening[1][0] == '`' and '`' in opening[2]):
            fence = (opening[1][0], len(opening[1])); output.append(''); continue
        if clean.startswith('    ') or clean.startswith('\t'):
            output.append(''); continue  # Indented code block, never anchor evidence.
        output.append(clean)
    visible = '\n'.join(output)
    return without_inline_code(visible) if drop_inline else visible


def headings(text):
    result, seen = [], Counter()
    for line in without_inline_code(visible_markdown(text), multiline_only=True).splitlines():
        m = re.match(r'^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?$', line)
        if m:
            base = slug(m[1]); suffix = seen[base]; seen[base] += 1
            result.append(base + (f'-{suffix}' if suffix else ''))
    return result


def anchors(text):
    visible = visible_markdown(text, drop_inline=True)
    explicit = re.findall(r'<a\s+[^>]*(?:id|name)=["\']([^"\']+)["\'][^>]*>', visible, re.I)
    all_ids = headings(text) + explicit
    return set(all_ids), [v for v, count in Counter(all_ids).items() if count > 1]


def markdown_targets(text):
    return re.findall(r'\]\(([^)]+)\)', visible_markdown(text, drop_inline=True))


def check_fragments(path, text, files):
    issues = []
    own, collisions = anchors(text)
    if collisions:
        issues.append('anchor_collision')
    for target in markdown_targets(text):
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        raw_path, _, fragment = target.partition('#')
        joined = Path(path).parent / unquote(raw_path) if raw_path else Path(path)
        parts = []
        for part in joined.parts:
            if part == '..':
                if not parts:
                    parts = None; break
                parts.pop()
            elif part != '.':
                parts.append(part)
        if parts is None:
            continue  # Existing external/placeholder links remain verifier policy.
        dest = '/'.join(parts)
        if fragment and dest in files and dest.endswith('.md'):
            ids, _ = anchors(files[dest].decode())
            if unquote(fragment) not in ids:
                issues.append('unresolved_fragment:' + target)
    return issues


def machine_tokens(text):
    """Only unequivocal identifiers: hashes, URLs and code spans without Cyrillic."""
    return {
        'hashes': Counter(re.findall(r'\b[0-9a-f]{40,64}\b', text)),
        'urls': Counter(re.findall(r'https?://[^\s)>]+', text)),
        'code': Counter(x for x in re.findall(r'(?<!`)`([^`\n]+)`(?!`)', text)
                        if not CYRILLIC.search(x)),
    }


def fenced_machine_blocks(text):
    blocks, active, content = [], None, []
    languages = {'sh','bash','shell','json','jsonc','yaml','yml','toml','python','javascript','typescript'}
    for line in text.splitlines(keepends=True):
        raw = line.rstrip('\r\n')
        if active:
            if re.fullmatch(r' {0,3}' + re.escape(active[0]) + '{' + str(active[1]) + r',}\s*', raw):
                if active[2] in languages:
                    blocks.append((active[2], ''.join(content)))
                active, content = None, []
            else:
                content.append(line)
        else:
            match = re.match(r'^ {0,3}(`{3,}|~{3,})([^\s`]*)\s*$', raw)
            if match:
                active = (match[1][0],len(match[1]),match[2])
    if active and active[2] in languages:
        raise ValueError('unclosed machine fence')
    return blocks


def shell_comment_prefix(line):
    """Recognize a plain shell trailing comment, never substitutions or quoted #."""
    if any(c in line for c in ('$', '`', '\\')):
        return None
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == '#' and (i == 0 or line[i-1].isspace()):
            return line[:i+1]
    return None


def example_description_only(previous, current):
    """One source-bound illustrative SKILL frontmatter, not arbitrary YAML data."""
    pattern = r'(  ---\n  name: skill-name\n  description: )([^\n]+)(\n  ---\n)'
    a, b = re.fullmatch(pattern, previous), re.fullmatch(pattern, current)
    return bool(a and b and CYRILLIC.search(a[2]) and not CYRILLIC.search(b[2]))


def machine_blocks_proof(old, new):
    a, b = fenced_machine_blocks(old), fenced_machine_blocks(new)
    if len(a) != len(b):
        raise ValueError('changed machine block count')
    for (lang, previous),(lang2,current) in zip(a,b):
        if lang != lang2:
            raise ValueError('changed machine block language')
        if previous == current:
            continue
        if lang in ('yaml','yml') and example_description_only(previous,current):
            continue
        if lang in ('json','jsonc','yaml','yml','toml'):
            raise ValueError('changed machine data')
        old_lines, new_lines = previous.splitlines(), current.splitlines()
        if len(old_lines) != len(new_lines):
            raise ValueError('changed machine block structure')
        for x,y in zip(old_lines,new_lines):
            if x == y:
                continue
            if lang in ('sh','bash','shell'):
                prefix = shell_comment_prefix(x)
                if prefix and CYRILLIC.search(x[len(prefix):]) and shell_comment_prefix(y) == prefix:
                    continue
            marker = '#' if lang in ('sh','bash','shell','python') else '//'
            # Only actual whole-line comments, never a marker inside an argument.
            if x.lstrip().startswith(marker) and CYRILLIC.search(x):
                if not y.lstrip().startswith(marker) or x[:len(x)-len(x.lstrip())] != y[:len(y)-len(y.lstrip())]:
                    raise ValueError('changed comment structure')
                continue
            # Permit translated plain echo display text, not machine arguments or
            # shell substitutions. All non-display source bytes remain identical.
            echo = re.fullmatch(r'(\s*echo\s+)(["\'])([^"\']*)(["\'])(\s*)', x)
            translated = re.fullmatch(r'(\s*echo\s+)(["\'])([^"\']*)(["\'])(\s*)', y)
            if echo and translated and CYRILLIC.search(echo[3]):
                if echo[2] != echo[4] or translated[2] != translated[4]:
                    raise ValueError('mismatched display quotes')
                if (echo[1],echo[2],echo[4],echo[5]) != (translated[1],translated[2],translated[4],translated[5]):
                    raise ValueError('changed display command')
                if any(c in echo[3] + translated[3] for c in '$`\\'):
                    raise ValueError('display substitution not translatable')
                continue
            raise ValueError('changed executable tokens')


def quoted_literals(text):
    # Decode the description value before extracting its user phrases: YAML's outer
    # quotes are syntax, not permission to exempt an entire untranslated description.
    sources = [text]
    if text.startswith('---\n'):
        front, _, body = text.partition('\n---\n')
        match = re.search(r'^description:(.*(?:\n[ \t]+.*)*)', front, re.M)
        sources = [body]
        if match:
            value = match[1].strip()
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]  # Retain doubled apostrophes as recorded source bytes.
            elif value.startswith(('>', '|')):
                value = re.sub(r'\s+', ' ', value[1:]).strip()
            sources.append(value)
    patterns = [r'"([^"\n]+)"', r'«([^»\n]+)»', r'“([^”\n]+)”', r'`([^`\n]+)`']
    return {x for source in sources for pattern in patterns
            for x in re.findall(pattern, source) if CYRILLIC.search(x)}


def english_coverage(old, new, literals):
    remaining = new
    old_slugs = set(headings(old))
    allowed_quotes = quoted_literals(old)
    for item in literals:
        if set(item) != {'text', 'reason'} or not item['reason'].strip():
            raise ValueError('invalid preserved literal record')
        value = item['text']
        if not isinstance(value, str) or not value or value not in new:
            raise ValueError('missing preserved literal')
        anchor = re.fullmatch(r'<a\s+(?:id|name)=["\']([^"\']+)["\']\s*></a>', value)
        allowed_anchor = anchor and anchor[1] in old_slugs
        # An exact original explicit anchor is also compatibility data.
        literal_token = (re.fullmatch(r'<[^<>\s]+>|[0-9]+[а-яА-Я]', value) and value in old)
        embedded_code_token = (not re.search(r'\s', value) and any(value in q for q in allowed_quotes))
        original_target = value in markdown_targets(old)
        # Original frontmatter keys are machine identifiers; values remain prose.
        front = old.split('\n---\n', 1)[0] if old.startswith('---\n') else ''
        frontmatter_key = value in re.findall(r'^([^\s:#]+):', front, re.M)
        # Protocol labels are data only in original label lists or label bullets.
        label = value.rstrip(':')
        protocol_label = (re.fullmatch(r'[А-ЯІЇЄҐ]+', label) and (
            re.search(r'^- ' + re.escape(label) + r':', old, re.M) or
            any(label in group.split(' / ') for group in
                re.findall(r'[А-ЯІЇЄҐ]+(?: / [А-ЯІЇЄҐ]+)+', old))))
        placeholder = (re.fullmatch(r'<[^<>\n]+>', value) and
                       any(value in q for q in re.findall(r'`([^`\n]+)`', old)))
        if not frontmatter_key and not protocol_label and not placeholder and not allowed_anchor and not literal_token and not embedded_code_token and not original_target and value not in allowed_quotes and not (value in old_slugs) and not (
                re.fullmatch(r'<a\s+[^>]+></a>', value) and value in old):
            raise ValueError('unjustified preserved literal')
        remaining = remaining.replace(value, '')
    if CYRILLIC.search(remaining):
        raise ValueError('untranslated or undeclared Cyrillic')
    # Explicit original user triggers in descriptions must survive individually.
    if old.startswith('---\n'):
        desc = old.split('\n---\n', 1)[0]
        # Quoted descriptive prose is not necessarily a literal routing trigger.
        # Explicit trigger lists and quoted user requests are compatibility data.
        marker = re.search(r'тригер[^:]*?[: ]', desc, re.I)
        # Trigger/request clauses stop at a sentence boundary; later quoted
        # explanatory prose is not a routing alias (e.g. measured 'savings').
        trigger_source = desc[marker.start():].split('.', 1)[0] if marker else ''
        requests = re.findall(r'(?:питають|просить|запити)\s+([^.]*)', desc, re.I)
        trigger_source += ' ' + ' '.join(requests)
        requested = re.findall(r'просить\s+«([^»]+)»', desc)
        required = quoted_literals(trigger_source) | set(requested)
        # Simple quoted aliases in a description without other Cyrillic prose are
        # also explicit compatibility data (including the synthetic refusal case).
        if not marker:
            for value in quoted_literals(desc):
                stripped = desc.replace(value, '')
                if not CYRILLIC.search(stripped):
                    required.add(value)
        for value in required:
            if value not in new:
                raise ValueError('missing original trigger alias')



def canonical_target(path, target):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith('/'):
        return target
    raw, sep, fragment = target.partition('#')
    parts = []
    joined = Path(path).parent / unquote(raw) if raw else Path(path)
    for part in joined.parts:
        if part == '..' and parts and parts[-1] != '..':
            parts.pop()
        elif part != '.':
            parts.append(part)
    return '/'.join(parts) + (sep + fragment if sep else '')


def historical_targets(original, path, old, new):
    # Source/baseline provenance navigation is new; all old targets still required.
    old_targets = Counter(canonical_target(original, x) for x in markdown_targets(old))
    new_targets = Counter()
    for target in markdown_targets(new):
        resolved = canonical_target(path, target)
        if resolved.startswith(path + '#'):
            resolved = original + resolved[len(path):]
        new_targets[resolved] += 1
    if old_targets - new_targets:
        raise ValueError('historical link changed destination')


def canonical_records_digest(records):
    """SHA256 of UTF-8 JSON, sorted object keys, original array order.

    json.dumps default separators (comma-space / colon-space), ensure_ascii=False,
    indent=None, and no trailing newline. This reproduces the accepted amendment.
    """
    return digest(json.dumps(records, sort_keys=True, ensure_ascii=False).encode('utf-8'))


def restore_cleanup(path, raw):
    """Invert ONLY the exact accepted content delta; reject any unrelated edit."""
    contract = CLEANUP_FILES[path]
    if digest(raw) != contract['proposed_sha256']:
        raise ValueError('cleanup proposed content mismatch:' + path)
    text = raw.decode()
    for hunk in reversed(contract['hunks']):
        if text[hunk['start']:hunk['end']] != hunk['after']:
            raise ValueError('cleanup operation mismatch:' + path)
        text = text[:hunk['start']] + hunk['before'] + text[hunk['end']:]
    restored = text.encode()
    if digest(restored) != contract['before_sha256']:
        raise ValueError('cleanup reconstructed source mismatch:' + path)
    return restored


def cleanup_content_proof(before, data):
    """Keep the immutable baseline and reconstruct precleanup comparison content.

    No broad URL, command or historical-document exemption is introduced. The
    baseline itself is authenticated by load_baseline; source hash equality is
    additionally required for the two formerly frozen historical originals.
    """
    restored = dict(data)
    if not any(n in data or n in before for n in CLEANUP_FILES):
        return restored  # Synthetic full-tree fixtures without cleanup paths.
    for path, contract in CLEANUP_FILES.items():
        if path not in data:
            raise ValueError('cleanup missing file:' + path)
        restored[path] = restore_cleanup(path, data[path])
        if contract['historical_original'] and restored[path] != before.get(path):
            raise ValueError('cleanup original baseline mismatch:' + path)
    return restored


def cleanup_metadata_proof(before, data):
    """Prove exact ordered deletions and their immutable source occurrences.

    Returned arrays are the sole approved metadata normalization. All other
    source-map fields still pass the original recursive identity proof.
    """
    if 'provenance/link-exceptions.json' not in before and 'provenance/link-exceptions.json' not in data:
        return {}  # Synthetic fixtures without the real cleanup metadata.
    approved = {}
    removed_occurrences = []
    for path, contract in CLEANUP_METADATA.items():
        old, new = json.loads(before[path]), json.loads(data[path])
        key = contract['key']
        original, retained = old[key], new[key]
        if canonical_records_digest(original) != contract['before_records_sha256']:
            raise ValueError('cleanup metadata baseline mismatch:' + path)
        if canonical_records_digest(retained) != contract['after_records_sha256']:
            raise ValueError('cleanup retained records mismatch:' + path)
        # Ordered subsequence subtraction preserves duplicates and cannot silently
        # accept edits/reordering through ordinary set membership.
        removed, cursor = [], 0
        for record in original:
            if cursor < len(retained) and record == retained[cursor]:
                cursor += 1
            else:
                removed.append(record)
        if cursor != len(retained):
            raise ValueError('cleanup records not pure deletion:' + path)
        if (len(removed) != contract['removed_records'] or
                len(retained) != contract['retained_records'] or
                canonical_records_digest(removed) != contract['removed_records_sha256']):
            raise ValueError('cleanup removed records mismatch:' + path)
        occurrences = Counter((row['file'], row['target']) for row in removed)
        for (filename, target), count in occurrences.items():
            if filename not in CLEANUP_FILES or filename not in before:
                raise ValueError('cleanup removed record outside content scope:' + path)
            if before[filename].decode().count('](' + target + ')') != count:
                raise ValueError('cleanup removed record lacks original occurrence:' + path)
            if '](' + target + ')' in data[filename].decode():
                raise ValueError('cleanup removed record still present:' + path)
        removed_occurrences.append(occurrences)
        if key == 'references':
            if (digest(before[path]) != contract['before_sha256'] or
                    digest(data[path]) != contract['proposed_sha256']):
                raise ValueError('cleanup link exceptions bytes mismatch:' + path)
            if {k:v for k,v in old.items() if k != key} != {k:v for k,v in new.items() if k != key}:
                raise ValueError('cleanup link exceptions policy changed:' + path)
        approved[path] = retained
    if any(x != removed_occurrences[0] for x in removed_occurrences[1:]):
        raise ValueError('cleanup metadata occurrence tables disagree')
    return approved


def metadata_proof(before, data, allowed):
    """Preserve upstream identity fields and old transformations, verify current hashes."""
    cleanup_arrays = cleanup_metadata_proof(before, data)
    for filename in ('source-map.json', 'layout-migration.json', 'authorized-additions.json'):
        name = 'provenance/' + filename
        old, new = json.loads(before[name]), json.loads(data[name])
        if name in cleanup_arrays:
            old[CLEANUP_METADATA[name]['key']] = cleanup_arrays[name]
        def walk(a, b, context=None, key=''):
            if isinstance(a, dict):
                if not isinstance(b, dict) or not set(a) <= set(b):
                    raise ValueError('metadata removed field')
                context = a.get('destination', a.get('new_path', a.get('path', context)))
                for k, value in a.items():
                    walk(value, b[k], context, k)
            elif isinstance(a, list):
                if not isinstance(b, list) or len(b) < len(a):
                    raise ValueError('metadata removed list item')
                if key == 'transformations':
                    if b[:len(a)] != a or any(not isinstance(x,str) for x in b[len(a):]):
                        raise ValueError('metadata rewrote historical transformation')
                else:
                    for i,value in enumerate(a):
                        walk(value,b[i],context,key)
                    if len(b) != len(a) and key != 'files':
                        raise ValueError('metadata unexpected list addition')
                    for row in b[len(a):]:
                        if row.get('destination') not in allowed or row['destination'] in before:
                            raise ValueError('metadata undeclared authored addition')
            elif a != b:
                if key in ('sha256','new_sha256','after_sha256') and context in data:
                    if b != digest(data[context]):
                        raise ValueError('metadata current digest mismatch')
                elif key == 'before_sha256' and filename == 'authorized-additions.json' and context in data:
                    pass  # Verified against the exact preserved append below.
                elif key == 'action' and context in allowed and b == 'updated':
                    pass
                else:
                    raise ValueError('metadata historical identity changed')
        walk(old,new)
        if filename == 'authorized-additions.json':
            for a,b in zip(old['adaptations'],new['adaptations']):
                name = a.get('path', a.get('destination'))
                append = a['append'].encode()
                if not data[name].endswith(append) or a['append'] != b['append']:
                    raise ValueError('authorized English append changed')
                if b['before_sha256'] != digest(data[name][:-len(append)]) or b['after_sha256'] != digest(data[name]):
                    raise ValueError('adaptation base/result hash mismatch')


def check_payload(root, data):
    manifest = json.loads(data['release-manifest.json'])
    names = [row['path'] for row in manifest['files']]
    if len(names) != len(set(names)):
        raise ValueError('duplicate current manifest path')
    checks = {}
    for row in manifest['files']:
        if digest(data[row['path']]) != row['sha256']:
            raise ValueError('current payload hash mismatch:' + row['path'])
        checks[row['path']] = row['sha256']
    checks['release-manifest.json'] = digest(data['release-manifest.json'])
    expected = ''.join(checks[n] + '  ' + n + '\n' for n in sorted(checks))
    if data['checksums.sha256'].decode() != expected:
        raise ValueError('current checksum closure mismatch')
    return manifest


def verify(root, baseline):
    result = {'status': 'FAIL', 'issues': [], 'skills': [], 'semantic_equivalence': 'NOT_TESTED',
              'native_routing': 'NOT_TESTED', 'baseline_commit': BASE_COMMIT}
    try:
        before = load_baseline(baseline)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status='BLOCKED', issues=['baseline_unavailable_or_invalid'])
        return result
    issues = result['issues']
    result['skills'] = [{'path':n,'status':'UNVERIFIED'} for n in sorted(before) if n.endswith('/SKILL.md')]
    allowed = {row['path']: row for row in ALLOWLIST}
    try:
        found = inventory(root)
        archive = json.loads(before['provenance/research-archive.json'])['files']
        expected = set(before) | {n for n, row in allowed.items() if row['operation'] == 'create'}
        extras = found - expected
        for n in extras:
            if n not in archive or digest(regular(root, n)) != archive[n]:
                issues.append('unexpected_file:' + n)
        if expected - found:
            issues.extend('missing_file:' + n for n in sorted(expected - found))
        data = {n: regular(root, n) for n in expected & found}
        structural_data = cleanup_content_proof(before, data)
        for n, raw in before.items():
            if n not in allowed and data.get(n) != raw:
                issues.append('frozen_file_changed:' + n)
        manifest = check_payload(root, data)
        if {r['path'] for r in manifest['files']} | {'release-manifest.json','checksums.sha256'} != expected:
            issues.append('manifest_inventory_mismatch')
        metadata_proof(before, data, allowed)
        old_manifest = json.loads(before['release-manifest.json'])
        if {k:v for k,v in manifest.items() if k != 'files'} != {k:v for k,v in old_manifest.items() if k != 'files'}:
            issues.append('manifest_policy_changed')
        provenance = json.loads(data['provenance/english-translations.json'])
        if provenance['schema_version'] != 1 or provenance['baseline_commit'] != BASE_COMMIT:
            issues.append('provenance_identity')
        records = provenance['records']
        rows = {r['path']: r for r in records}
        content = {n for n, r in allowed.items() if r['class'] in ('current_docs','skills','guard_diagnostics_only','historical_translation')}
        if len(rows) != len(records) or set(rows) != content:
            issues.append('provenance_scope')
        for n in sorted(content):
            if n not in data or n not in rows:
                continue
            row, contract = rows[n], allowed[n]
            historical = contract['class'] == 'historical_translation'
            original = contract.get('original') if historical else n
            old = before[original].decode(); new = structural_data[n].decode()
            if row['class'] != contract['class'] or row['sha256'] != digest(data[n]):
                issues.append('provenance_current_hash:' + n)
            if row['base_sha256'] != (None if historical else digest(before[n])):
                issues.append('provenance_base_hash:' + n)
            if historical:
                try:
                    historical_targets(original, n, old, new)
                except ValueError:
                    issues.append('historical_link_changed:' + n)
                if row.get('original') != original or row.get('original_sha256') != digest(before[original]):
                    issues.append('historical_mapping:' + n)
                if original not in new or digest(before[original]) not in new or BASE_COMMIT not in new:
                    issues.append('historical_banner:' + n)
            try:
                if n in DESCRIPTION_PATHS and description_parts(old) != description_parts(new):
                    raise ValueError('description-only body or other keys changed')
                if contract['class'] == 'guard_diagnostics_only':
                    guard_proof(old, new)
                else:
                    # Existing explicit anchors and old heading fragments must resolve.
                    old_ids, _ = anchors(old); new_ids, _ = anchors(new)
                    if not old_ids <= new_ids:
                        raise ValueError('lost heading compatibility anchor')
                    if not historical and Counter(markdown_targets(old)) != Counter(markdown_targets(new)):
                        raise ValueError('changed Markdown target')
                    old_tokens, new_tokens = machine_tokens(old), machine_tokens(new)
                    for kind in ('hashes','urls','code'):
                        # Translated inline prose may become an English code span;
                        # historical banners add source hashes/links. Existing tokens
                        # still must survive with their original multiplicity.
                        if old_tokens[kind] - new_tokens[kind]:
                            raise ValueError('changed command/id/URL/code span')
                        if not historical and kind != 'code' and old_tokens[kind] != new_tokens[kind]:
                            raise ValueError('unexpected hash/URL')
                    machine_blocks_proof(old, new)
                    issues.extend(code + ':' + n for code in check_fragments(n, new, data))
                english_coverage(old, new, row['preserved_literals'])
            except ValueError as exc:
                issues.append(str(exc) + ':' + n)
        skills = sorted(n for n in before if n.endswith('/SKILL.md'))
        result['skills'] = []
        for n in skills:
            changed = data.get(n) != before[n]
            related = [x for x in issues if x.endswith(':' + n)]
            result['skills'].append({'path':n,'changed':changed,'authorized':n in allowed,
                                     'status':'FAIL' if related or (changed and n not in allowed) else ('AUTHORIZED_TRANSLATION' if changed else 'FROZEN')})
        if len(skills) != 74:
            issues.append('skill_count_not_74')
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, UnicodeError) as exc:
        issues.append('invalid_tree_or_contract:' + type(exc).__name__ + ':' + (n if 'n' in locals() else 'inventory'))
    result['status'] = 'FAIL' if issues else 'PASS'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.root.absolute(), args.baseline.absolute())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
