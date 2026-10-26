#!/usr/bin/env python3
"""Offline structural translation proof against an explicit immutable baseline.

This does not prove semantic equivalence or native routing. Independent review is
required. No scripts from either tree are imported or executed.
"""
import argparse
import ast
from collections import Counter
import hashlib
import html
from html.parser import HTMLParser
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


# Filled only from the independently reviewed exact anchor migration contract.
ANCHOR_COMMIT = '8b42ad93f0599dddd059f91f0bc47347daba6301'
ANCHOR_MANIFEST = 'cb4ae76f99504a76de1f4755b8b4344ee9e8b205226c0e8580886a042e938116'
ANCHOR_FILES = {
    'README.md': {'path': 'README.md', 'pre_anchor_sha256': 'e56cac5abab469bbf9ba3ce12f4696a84de4e7335fd611c5124782c889805e52', 'current_sha256': '5fe5dd6bee3222b099ed1c78e49070ff7b5973a08590262ed830bdda0c9d4336', 'removed_ids': [{'old_id': 'що-адаптовано-з-ecc', 'new_id': 'what-was-adapted-from-ecc', 'binding': 'What was adapted from ECC', 'line': 22}, {'old_id': 'почати-через-ai-три-сценарії', 'new_id': 'getting-started-with-ai-three-scenarios', 'binding': 'Getting started with AI: three scenarios', 'line': 77}, {'old_id': 'ai-factory-як-локальний-tooling-агента-в-проєкті', 'new_id': 'ai-factory-as-project-local-agent-tooling', 'binding': 'AI Factory as project-local agent tooling', 'line': 96}, {'old_id': 'що-реалізовано-а-що-потрібно-перевірити', 'new_id': 'what-is-implemented-and-what-needs-verification', 'binding': 'What is implemented and what needs verification', 'line': 124}, {'old_id': 'промпт-1--перевірити-й-безпечно-підключити-локально', 'new_id': 'prompt-1--inspect-and-safely-connect-local-tooling', 'binding': 'Prompt 1 — inspect and safely connect local tooling', 'line': 166}, {'old_id': 'промпт-2--почати-або-продовжити-задачу', 'new_id': 'prompt-2--start-or-resume-a-task', 'binding': 'Prompt 2 — start or resume a task', 'line': 187}, {'old_id': 'промпт-3--перевірено-оновити-package', 'new_id': 'prompt-3--perform-a-verified-package-update', 'binding': 'Prompt 3 — perform a verified package update', 'line': 202}, {'old_id': 'один-файл--одна-роль', 'new_id': 'one-file--one-role', 'binding': 'One file — one role', 'line': 220}, {'old_id': 'безпечне-використання-та-оновлення', 'new_id': 'safe-use-and-updates', 'binding': 'Safe use and updates', 'line': 227}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 1775, 'end': 1775, 'before': '<a id="що-адаптовано-з-ecc"></a>\n', 'after': ''}, {'start': 6716, 'end': 6716, 'before': '<a id="почати-через-ai-три-сценарії"></a>\n', 'after': ''}, {'start': 9513, 'end': 9513, 'before': '<a id="ai-factory-як-локальний-tooling-агента-в-проєкті"></a>\n', 'after': ''}, {'start': 11013, 'end': 11013, 'before': '<a id="що-реалізовано-а-що-потрібно-перевірити"></a>\n', 'after': ''}, {'start': 14061, 'end': 14061, 'before': '<a id="промпт-1--перевірити-й-безпечно-підключити-локально"></a>\n', 'after': ''}, {'start': 15257, 'end': 15257, 'before': '<a id="промпт-2--почати-або-продовжити-задачу"></a>\n', 'after': ''}, {'start': 16012, 'end': 16012, 'before': '<a id="промпт-3--перевірено-оновити-package"></a>\n', 'after': ''}, {'start': 17046, 'end': 17046, 'before': '<a id="один-файл--одна-роль"></a>\n', 'after': ''}, {'start': 17805, 'end': 17805, 'before': '<a id="безпечне-використання-та-оновлення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="що-адаптовано-з-ecc"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="почати-через-ai-три-сценарії"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="ai-factory-як-локальний-tooling-агента-в-проєкті"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="що-реалізовано-а-що-потрібно-перевірити"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="промпт-1--перевірити-й-безпечно-підключити-локально"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="промпт-2--почати-або-продовжити-задачу"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 6, 'record': {'text': '<a id="промпт-3--перевірено-оновити-package"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 7, 'record': {'text': '<a id="один-файл--одна-роль"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 8, 'record': {'text': '<a id="безпечне-використання-та-оновлення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '2a0724fecf6bd2b401b4bc09290bee8ef4c0ec717b8b6e28c0b3c7cd22720bc3', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'adapters/legacy-planning/acceptance-spec-portable.md': {'path': 'adapters/legacy-planning/acceptance-spec-portable.md', 'pre_anchor_sha256': '1f17470e225fb180f7c322c7faf606c91c1ac5d2d8c6d0a6da41c40ba21859dc', 'current_sha256': '87573bf0588f4226f3467ea0a06c8405ac209ecebbd0697d4a23724ecc6775b0', 'removed_ids': [{'old_id': 'acceptance-spec--фіча-як-спостережувана-поведінка', 'new_id': 'acceptance-spec--a-feature-as-observable-behavior', 'binding': 'acceptance-spec — a feature as observable behavior', 'line': 8}, {'old_id': '1-збери-сценарії', 'new_id': '1-collect-scenarios', 'binding': '1. Collect scenarios', 'line': 19}, {'old_id': '2-заповни-таблицю', 'new_id': '2-fill-in-the-table', 'binding': '2. Fill in the table', 'line': 31}, {'old_id': '3-привяжи-до-роботи', 'new_id': '3-link-it-to-the-work', 'binding': '3. Link it to the work', 'line': 47}, {'old_id': '4-завершення', 'new_id': '4-completion', 'binding': '4. Completion', 'line': 55}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 732, 'end': 732, 'before': '<a id="acceptance-spec--фіча-як-спостережувана-поведінка"></a>\n', 'after': ''}, {'start': 1222, 'end': 1222, 'before': '<a id="1-збери-сценарії"></a>\n', 'after': ''}, {'start': 1780, 'end': 1780, 'before': '<a id="2-заповни-таблицю"></a>\n', 'after': ''}, {'start': 2585, 'end': 2585, 'before': '<a id="3-привяжи-до-роботи"></a>\n', 'after': ''}, {'start': 2983, 'end': 2983, 'before': '<a id="4-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="acceptance-spec--фіча-як-спостережувана-поведінка"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="1-збери-сценарії"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="2-заповни-таблицю"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="3-привяжи-до-роботи"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="4-завершення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '6fd0c22eb7948665c10a20f17ba726d13bceb0eaede8424cd81f02d386ae2fe1', 'current_literals_sha256': '586cc61b952ff09ef5e659378139ae84c33f86c0f077619e520872d9b5b97356'},
    'adapters/legacy-planning/cto-research-portable.md': {'path': 'adapters/legacy-planning/cto-research-portable.md', 'pre_anchor_sha256': '98c8fe76d50be42e91397022951ed7b34fb5cd958e5a13500527b054f977bf46', 'current_sha256': 'e9a257eaf372379fa1b9283042f7ae833a30702b0338a12a75ba01e4366f074e', 'removed_ids': [{'old_id': 'cto-research--брифінг-перед-імплементацією', 'new_id': 'cto-research--a-pre-implementation-briefing', 'binding': 'cto-research — a pre-implementation briefing', 'line': 8}, {'old_id': '1-знайди-дім-брифінгу', 'new_id': '1-find-the-briefings-home', 'binding': "1. Find the briefing's home", 'line': 17}, {'old_id': '2-гейт-свіжості-перший-крок-коли-файл-уже-є', 'new_id': '2-freshness-gate-the-first-step-when-the-file-exists', 'binding': '2. Freshness gate (the first step when the file exists)', 'line': 25}, {'old_id': '3-збери-по-пяти-осях', 'new_id': '3-research-five-axes', 'binding': '3. Research five axes', 'line': 40}, {'old_id': '4-напиши-брифінг', 'new_id': '4-write-the-briefing', 'binding': '4. Write the briefing', 'line': 56}, {'old_id': '5-завершення', 'new_id': '5-completion', 'binding': '5. Completion', 'line': 74}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 780, 'end': 780, 'before': '<a id="cto-research--брифінг-перед-імплементацією"></a>\n', 'after': ''}, {'start': 1243, 'end': 1243, 'before': '<a id="1-знайди-дім-брифінгу"></a>\n', 'after': ''}, {'start': 1917, 'end': 1917, 'before': '<a id="2-гейт-свіжості-перший-крок-коли-файл-уже-є"></a>\n', 'after': ''}, {'start': 3217, 'end': 3217, 'before': '<a id="3-збери-по-пяти-осях"></a>\n', 'after': ''}, {'start': 4205, 'end': 4205, 'before': '<a id="4-напиши-брифінг"></a>\n', 'after': ''}, {'start': 5039, 'end': 5039, 'before': '<a id="5-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="cto-research--брифінг-перед-імплементацією"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="1-знайди-дім-брифінгу"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="2-гейт-свіжості-перший-крок-коли-файл-уже-є"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="3-збери-по-пяти-осях"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="4-напиши-брифінг"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="5-завершення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'f21de77f0b18ca630212f95cd2d3981baf86314d42e9a1bfa92814e7be1832bb', 'current_literals_sha256': '4173db820c12ba6afd01478f83c703d055c7be7d7723d66375402ec58321bdc9'},
    'adapters/legacy-planning/plan-critique-portable.md': {'path': 'adapters/legacy-planning/plan-critique-portable.md', 'pre_anchor_sha256': '6a502ecce4468c393d72dd24867f5689453db67bed92db083bd2e93092a4533c', 'current_sha256': '17a87bc9795a7621cac491d76b4d9f79468858ed5735e2ff8d96b46d0aa0d04d', 'removed_ids': [{'old_id': 'plan-critique--чотири-лінзи-по-плану', 'new_id': 'plan-critique--four-lenses-on-a-plan', 'binding': 'plan-critique — four lenses on a plan', 'line': 8}, {'old_id': '1-підготуй-матеріал', 'new_id': '1-prepare-the-material', 'binding': '1. Prepare the material', 'line': 18}, {'old_id': '2-прожени-чотири-лінзи-паралельно', 'new_id': '2-run-four-lenses-in-parallel', 'binding': '2. Run four lenses in parallel', 'line': 24}, {'old_id': 'лінза-що-не-повернулась', 'new_id': 'a-lens-that-did-not-return', 'binding': 'A lens that did not return', 'line': 51}, {'old_id': '3-зведи', 'new_id': '3-consolidate', 'binding': '3. Consolidate', 'line': 64}, {'old_id': '4-завершення', 'new_id': '4-completion', 'binding': '4. Completion', 'line': 72}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 749, 'end': 749, 'before': '<a id="plan-critique--чотири-лінзи-по-плану"></a>\n', 'after': ''}, {'start': 1204, 'end': 1204, 'before': '<a id="1-підготуй-матеріал"></a>\n', 'after': ''}, {'start': 1425, 'end': 1425, 'before': '<a id="2-прожени-чотири-лінзи-паралельно"></a>\n', 'after': ''}, {'start': 2812, 'end': 2812, 'before': '<a id="лінза-що-не-повернулась"></a>\n', 'after': ''}, {'start': 3651, 'end': 3651, 'before': '<a id="3-зведи"></a>\n', 'after': ''}, {'start': 3941, 'end': 3941, 'before': '<a id="4-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="plan-critique--чотири-лінзи-по-плану"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="1-підготуй-матеріал"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="2-прожени-чотири-лінзи-паралельно"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="лінза-що-не-повернулась"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="3-зведи"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="4-завершення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '2a97d19b8b0b7918b1f49d4c40ad4cfc8cfd59acde2726c2bd402078d7c81360', 'current_literals_sha256': '655224872c2052520214d9e8da592052236a83864a97e67ca666c62de33dc92c'},
    'adapters/legacy-planning/plan-defense-portable.md': {'path': 'adapters/legacy-planning/plan-defense-portable.md', 'pre_anchor_sha256': '6e25dffb7d39f18b9977ce480c4f3e6f5cc01516eb4b57276741276489ef14e7', 'current_sha256': '47df066bc9782a959461627599dd7fd2c76cd2defd3dd38d088b92efe2ddbadd', 'removed_ids': [{'old_id': 'plan-defense--пять-питань-на-які-план-відповідає-рядком', 'new_id': 'plan-defense--five-questions-the-plan-answers-with-a-line', 'binding': 'plan-defense — five questions the plan answers with a line', 'line': 8}, {'old_id': 'питання', 'new_id': 'questions', 'binding': 'Questions', 'line': 17}, {'old_id': 'форма-відповіді', 'new_id': 'answer-format', 'binding': 'Answer format', 'line': 33}, {'old_id': 'завершення', 'new_id': 'completion', 'binding': 'Completion', 'line': 49}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 761, 'end': 761, 'before': '<a id="plan-defense--пять-питань-на-які-план-відповідає-рядком"></a>\n', 'after': ''}, {'start': 1203, 'end': 1203, 'before': '<a id="питання"></a>\n', 'after': ''}, {'start': 2241, 'end': 2241, 'before': '<a id="форма-відповіді"></a>\n', 'after': ''}, {'start': 2706, 'end': 2706, 'before': '<a id="завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="plan-defense--пять-питань-на-які-план-відповідає-рядком"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="питання"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="форма-відповіді"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="завершення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'b8377a415a2ca6f68310b1b73df273fdf8c32bddf0a67dc9ee7a3031d1e6892c', 'current_literals_sha256': 'a078b98314f3b94f6bec68f068e7d3b2252383b5aa4f95df7bafa639e85696b4'},
    'ai-factory/ai-factory-plan.md': {'path': 'ai-factory/ai-factory-plan.md', 'pre_anchor_sha256': '6fb45dd999978372b172872fd7682c8b8f9fc5c02c486d413d207507bb23c45f', 'current_sha256': '7af05303aa72a801c01ca5e9e16255897686aab85f9eee78c871d3d75de8166a', 'removed_ids': [{'old_id': 'ai-factory-з-чого-почати', 'new_id': 'ai-factory-where-to-start', 'binding': 'AI factory: where to start', 'line': 9}, {'old_id': 'обери-маршрут', 'new_id': 'choose-a-route', 'binding': 'Choose a route', 'line': 26}, {'old_id': 'навігація', 'new_id': 'navigation', 'binding': 'Navigation', 'line': 38}, {'old_id': 'передача-й-завершення', 'new_id': 'handoff-and-completion', 'binding': 'Handoff and completion', 'line': 52}, {'old_id': 'розмір-сесії-та-явний-handoff', 'new_id': 'session-size-and-explicit-handoff', 'binding': 'Session size and explicit handoff', 'line': 63}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 248, 'end': 248, 'before': '<a id="ai-factory-з-чого-почати"></a>\n', 'after': ''}, {'start': 1783, 'end': 1783, 'before': '<a id="обери-маршрут"></a>\n', 'after': ''}, {'start': 2590, 'end': 2590, 'before': '<a id="навігація"></a>\n', 'after': ''}, {'start': 3627, 'end': 3627, 'before': '<a id="передача-й-завершення"></a>\n', 'after': ''}, {'start': 4670, 'end': 4670, 'before': '<a id="розмір-сесії-та-явний-handoff"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="ai-factory-з-чого-почати"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="обери-маршрут"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="навігація"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="передача-й-завершення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="розмір-сесії-та-явний-handoff"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '6333b10c6591c9264994b744b54110814707857bebcc0d5e2b61cb410d0a5ae5', 'current_literals_sha256': 'ee266557bbf41f7fe9bb07f887ef09aba2e31215de61915cfac29c47aafdfbcc'},
    'ai-factory/crg.md': {'path': 'ai-factory/crg.md', 'pre_anchor_sha256': 'c09092aa902e551906f79e085c9cacb9ff1995439b65bf44da508b88cffdfb0c', 'current_sha256': '7c371ac34405a6f09cef56be4950e04631af002869e568f575897587c051da41', 'removed_ids': [{'old_id': 'перевірений-transport-і-schema', 'new_id': 'verified-transport-and-schema', 'binding': 'Verified transport and schema', 'line': 12}, {'old_id': 'freshness-перед-довірою', 'new_id': 'freshness-before-trust', 'binding': 'Freshness before trust', 'line': 32}, {'old_id': 'відновлення-без-зміни-source', 'new_id': 'recovery-without-changing-source', 'binding': 'Recovery without changing source', 'line': 42}, {'old_id': 'host-discovery-стан-перевірки', 'new_id': 'host-discovery-verification-status', 'binding': 'Host discovery: verification status', 'line': 51}, {'old_id': 'історичні-обмеження-доказів-2026-10-16', 'new_id': 'historical-evidence-limitations-2026-10-16', 'binding': 'Historical evidence limitations (2026-10-16)', 'line': 59}, {'old_id': 'cargo-завершений-active-refresh--snapshot-2026-10-17', 'new_id': 'cargo-completed-active-refresh--snapshot-2026-10-17', 'binding': 'Cargo: completed active refresh — snapshot 2026-10-17', 'line': 72}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 573, 'end': 573, 'before': '<a id="перевірений-transport-і-schema"></a>\n', 'after': ''}, {'start': 2180, 'end': 2180, 'before': '<a id="freshness-перед-довірою"></a>\n', 'after': ''}, {'start': 3578, 'end': 3578, 'before': '<a id="відновлення-без-зміни-source"></a>\n', 'after': ''}, {'start': 4669, 'end': 4669, 'before': '<a id="host-discovery-стан-перевірки"></a>\n', 'after': ''}, {'start': 6579, 'end': 6579, 'before': '<a id="історичні-обмеження-доказів-2026-10-16"></a>\n', 'after': ''}, {'start': 8961, 'end': 8961, 'before': '<a id="cargo-завершений-active-refresh--snapshot-2026-10-17"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="перевірений-transport-і-schema"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="freshness-перед-довірою"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="відновлення-без-зміни-source"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="host-discovery-стан-перевірки"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="історичні-обмеження-доказів-2026-10-16"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 6, 'record': {'text': '<a id="cargo-завершений-active-refresh--snapshot-2026-10-17"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '3ba84a141c570ca26693bebb81ad4be0ae6fa63969473b49b71d52e44ccbfe10', 'current_literals_sha256': 'd297c10084e7323ccca3f31bc5ab530036af30b73536e17112794a820df2cae6'},
    'ai-factory/feature-lifecycle.md': {'path': 'ai-factory/feature-lifecycle.md', 'pre_anchor_sha256': '35ce2cc6bc16d95c27f20296209bf3a395717e2d803ba71674c9d34c5021673e', 'current_sha256': 'f0a5063ca35e690ade5733ac8dfc3ca59a856350c9c61b5e91d776468d7a4758', 'removed_ids': [{'old_id': 'від-запиту-до-готовності-фічі', 'new_id': 'from-request-to-feature-readiness', 'binding': 'From request to feature readiness', 'line': 6}, {'old_id': 'startup-хто-виконує-критику-review-та-перевірки', 'new_id': 'startup-who-performs-critique-review-and-checks', 'binding': 'Startup: who performs critique, review and checks', 'line': 27}, {'old_id': 'вибір-маршруту', 'new_id': 'route-selection', 'binding': 'Route selection', 'line': 36}, {'old_id': 'як-викликати', 'new_id': 'how-to-invoke', 'binding': 'How to invoke', 'line': 45}, {'old_id': 'етапи', 'new_id': 'stages', 'binding': 'Stages', 'line': 52}, {'old_id': '1-scope-й-acceptance', 'new_id': '1-scope-and-acceptance', 'binding': '1. Scope and acceptance', 'line': 55}, {'old_id': '2-дослідження-та-свіжість-контексту', 'new_id': '2-research-and-context-freshness', 'binding': '2. Research and context freshness', 'line': 64}, {'old_id': '3-spec-і-план', 'new_id': '3-spec-and-plan', 'binding': '3. Spec and plan', 'line': 73}, {'old_id': '4-умовний-adr', 'new_id': '4-conditional-adr', 'binding': '4. Conditional ADR', 'line': 82}, {'old_id': '6-реалізація', 'new_id': '6-implementation', 'binding': '6. Implementation', 'line': 99}, {'old_id': '7-перевірки-й-browser-qa', 'new_id': '7-checks-and-browser-qa', 'binding': '7. Checks and browser QA', 'line': 108}, {'old_id': '8-незалежне-ревю', 'new_id': '8-independent-review', 'binding': '8. Independent review', 'line': 117}, {'old_id': '9-виправлення-й-повторний-gate', 'new_id': '9-fixes-and-repeated-gate', 'binding': '9. Fixes and repeated gate', 'line': 127}, {'old_id': '10-документація-handoff-і-readiness-for-landing', 'new_id': '10-documentation-handoff-and-readiness-for-landing', 'binding': '10. Documentation, handoff and readiness for landing', 'line': 136}, {'old_id': 'адаптація-до-трьох-репозиторіїв', 'new_id': 'adaptation-to-three-repositories', 'binding': 'Adaptation to three repositories', 'line': 145}, {'old_id': 'відновлення-з-середини', 'new_id': 'resuming-from-the-middle', 'binding': 'Resuming from the middle', 'line': 156}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 89, 'end': 89, 'before': '<a id="від-запиту-до-готовності-фічі"></a>\n', 'after': ''}, {'start': 3163, 'end': 3163, 'before': '<a id="startup-хто-виконує-критику-review-та-перевірки"></a>\n', 'after': ''}, {'start': 4807, 'end': 4807, 'before': '<a id="вибір-маршруту"></a>\n', 'after': ''}, {'start': 6388, 'end': 6388, 'before': '<a id="як-викликати"></a>\n', 'after': ''}, {'start': 7282, 'end': 7282, 'before': '<a id="етапи"></a>\n', 'after': ''}, {'start': 7293, 'end': 7293, 'before': '<a id="1-scope-й-acceptance"></a>\n', 'after': ''}, {'start': 8186, 'end': 8186, 'before': '<a id="2-дослідження-та-свіжість-контексту"></a>\n', 'after': ''}, {'start': 9371, 'end': 9371, 'before': '<a id="3-spec-і-план"></a>\n', 'after': ''}, {'start': 10583, 'end': 10583, 'before': '<a id="4-умовний-adr"></a>\n', 'after': ''}, {'start': 12485, 'end': 12485, 'before': '<a id="6-реалізація"></a>\n', 'after': ''}, {'start': 13441, 'end': 13441, 'before': '<a id="7-перевірки-й-browser-qa"></a>\n', 'after': ''}, {'start': 15470, 'end': 15470, 'before': '<a id="8-незалежне-ревю"></a>\n', 'after': ''}, {'start': 17201, 'end': 17201, 'before': '<a id="9-виправлення-й-повторний-gate"></a>\n', 'after': ''}, {'start': 18009, 'end': 18009, 'before': '<a id="10-документація-handoff-і-readiness-for-landing"></a>\n', 'after': ''}, {'start': 19164, 'end': 19164, 'before': '<a id="адаптація-до-трьох-репозиторіїв"></a>\n', 'after': ''}, {'start': 21084, 'end': 21084, 'before': '<a id="відновлення-з-середини"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="від-запиту-до-готовності-фічі"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="startup-хто-виконує-критику-review-та-перевірки"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="вибір-маршруту"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="як-викликати"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="етапи"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="1-scope-й-acceptance"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 6, 'record': {'text': '<a id="2-дослідження-та-свіжість-контексту"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 7, 'record': {'text': '<a id="3-spec-і-план"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 8, 'record': {'text': '<a id="4-умовний-adr"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 9, 'record': {'text': '<a id="6-реалізація"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 10, 'record': {'text': '<a id="7-перевірки-й-browser-qa"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 11, 'record': {'text': '<a id="8-незалежне-ревю"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 12, 'record': {'text': '<a id="9-виправлення-й-повторний-gate"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 13, 'record': {'text': '<a id="10-документація-handoff-і-readiness-for-landing"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 14, 'record': {'text': '<a id="адаптація-до-трьох-репозиторіїв"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 15, 'record': {'text': '<a id="відновлення-з-середини"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'b61f6782a517d4f2a69c9d0d2b87429a579f8d682cf5db9afca0d6afebc15124', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'ai-factory/models.md': {'path': 'ai-factory/models.md', 'pre_anchor_sha256': 'c58d9d766c6c0361e371b008336966ec3d8004140615d26081b7c7f0aa673179', 'current_sha256': '44784eeef678b26c33e4b6c9776d1b436df5be89bf818853d05371ac6d98c9a8', 'removed_ids': [{'old_id': 'bindings-і-рівень-підтвердження', 'new_id': 'bindings-and-level-of-confirmation', 'binding': 'Bindings and level of confirmation', 'line': 20}, {'old_id': 'ліміти-роботи', 'new_id': 'work-limits', 'binding': 'Work limits', 'line': 38}, {'old_id': 'crg-і-мінімальний-handoff', 'new_id': 'crg-and-minimal-handoff', 'binding': 'CRG and minimal handoff', 'line': 47}, {'old_id': 'докази-доступності', 'new_id': 'evidence-of-availability', 'binding': 'Evidence of availability', 'line': 54}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 1513, 'end': 1513, 'before': '<a id="bindings-і-рівень-підтвердження"></a>\n', 'after': ''}, {'start': 3832, 'end': 3832, 'before': '<a id="ліміти-роботи"></a>\n', 'after': ''}, {'start': 4849, 'end': 4849, 'before': '<a id="crg-і-мінімальний-handoff"></a>\n', 'after': ''}, {'start': 5561, 'end': 5561, 'before': '<a id="докази-доступності"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="bindings-і-рівень-підтвердження"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="ліміти-роботи"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="crg-і-мінімальний-handoff"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="докази-доступності"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'bc9a1b3b31391f5353d5e36d95af9f32678a17cc66827bf39e119ff228bd9a76', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'ai-factory/onboarding/change-protocol.md': {'path': 'ai-factory/onboarding/change-protocol.md', 'pre_anchor_sha256': '25d489463380d53651d16120fd4ee1551b17fec83199aa64797d55a43d135808', 'current_sha256': '19c0e51d44f318840357fee0da21563eace9499ba1a51d22f6a328f53d5a0c17', 'removed_ids': [{'old_id': 'additive-зміна-повтор-і-guarded-restore', 'new_id': 'additive-change-repeat-and-guarded-restore', 'binding': 'Additive change, repeat and guarded restore', 'line': 1}, {'old_id': 'перед-записом', 'new_id': 'before-writing', 'binding': 'Before writing', 'line': 8}, {'old_id': 'restore-лише-власного-застосованого-diff', 'new_id': 'restore-only-your-own-applied-diff', 'binding': 'Restore only your own applied diff', 'line': 17}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="additive-зміна-повтор-і-guarded-restore"></a>\n', 'after': ''}, {'start': 397, 'end': 397, 'before': '<a id="перед-записом"></a>\n', 'after': ''}, {'start': 2040, 'end': 2040, 'before': '<a id="restore-лише-власного-застосованого-diff"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="additive-зміна-повтор-і-guarded-restore"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="перед-записом"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="restore-лише-власного-застосованого-diff"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '58c28befefe5131c800e9b37c4c0581c9a4a8aa6a593a166801632abd99de3a5', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'ai-factory/onboarding.md': {'path': 'ai-factory/onboarding.md', 'pre_anchor_sha256': 'd01f5d0e512897466b2f3c4e77cbcc4e93f22e3ecbbce70a5a252046cfc4ba45', 'current_sha256': '5fcf831d1c47b6517c32457a96b2fe0060c5921b9ed715212ef76f9becced1e8', 'removed_ids': [{'old_id': 'підключення-ai-factory-до-іншого-репозиторію', 'new_id': 'connecting-ai-factory-to-another-repository', 'binding': 'Connecting AI Factory to another repository', 'line': 3}, {'old_id': 'один-стартовий-запит', 'new_id': 'one-starting-request', 'binding': 'One starting request', 'line': 10}, {'old_id': 'швидкий-початок', 'new_id': 'quick-start', 'binding': 'Quick start', 'line': 21}, {'old_id': 'checklist-адаптації', 'new_id': 'adaptation-checklist', 'binding': 'Adaptation checklist', 'line': 43}, {'old_id': 'applicability-перевірок', 'new_id': 'check-applicability', 'binding': 'Check applicability', 'line': 60}, {'old_id': 'рівні-підтвердження', 'new_id': 'levels-of-confirmation', 'binding': 'Levels of confirmation', 'line': 77}, {'old_id': 'перевірка-перед-повторним-використанням', 'new_id': 'verification-before-reuse', 'binding': 'Verification before reuse', 'line': 90}, {'old_id': 'obsidian-перевірка-та-погоджена-синхронізація', 'new_id': 'obsidian-verification-and-agreed-synchronization', 'binding': 'Obsidian: verification and agreed synchronization', 'line': 116}], 'changed_targets': [{'old_target': 'review-handoff.md#перед-початком-роботи', 'new_target': 'review-handoff.md#before-starting-work', 'count': 1, 'line': 19}], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 230, 'end': 230, 'before': '<a id="підключення-ai-factory-до-іншого-репозиторію"></a>\n', 'after': ''}, {'start': 864, 'end': 864, 'before': '<a id="один-стартовий-запит"></a>\n', 'after': ''}, {'start': 1963, 'end': 1983, 'before': 'перед-початком-роботи', 'after': 'before-starting-work'}, {'start': 2275, 'end': 2275, 'before': '<a id="швидкий-початок"></a>\n', 'after': ''}, {'start': 4925, 'end': 4925, 'before': '<a id="checklist-адаптації"></a>\n', 'after': ''}, {'start': 7336, 'end': 7336, 'before': '<a id="applicability-перевірок"></a>\n', 'after': ''}, {'start': 9416, 'end': 9416, 'before': '<a id="рівні-підтвердження"></a>\n', 'after': ''}, {'start': 10281, 'end': 10281, 'before': '<a id="перевірка-перед-повторним-використанням"></a>\n', 'after': ''}, {'start': 13222, 'end': 13222, 'before': '<a id="obsidian-перевірка-та-погоджена-синхронізація"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="підключення-ai-factory-до-іншого-репозиторію"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="один-стартовий-запит"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="швидкий-початок"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="checklist-адаптації"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="applicability-перевірок"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 6, 'record': {'text': '<a id="рівні-підтвердження"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 7, 'record': {'text': '<a id="перевірка-перед-повторним-використанням"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 9, 'record': {'text': '<a id="obsidian-перевірка-та-погоджена-синхронізація"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 10, 'record': {'text': 'review-handoff.md#перед-початком-роботи', 'reason': 'Source-defined invocation, external matching label, historical identifier or compatibility link; English explanation accompanies non-obvious literals.'}}], 'pre_literals_sha256': '27a0d73ed31f5c1a6db19b9de626c4700d672103c621da4d9af0eb4cb24417fd', 'current_literals_sha256': 'f7c18c0cb107e611d686be8595459bf90fdbdfc2218c47bb4f1a2dfe01526051'},
    'ai-factory/review-handoff.md': {'path': 'ai-factory/review-handoff.md', 'pre_anchor_sha256': '57048b2880d0afda592710bfafb153ff94c1dbcf0b97f904443741857f114813', 'current_sha256': 'd0393a01acb207feae9f112df726e7813c79ac20445713b55a92961af4d20740', 'removed_ids': [{'old_id': 'startup-routing-та-передача-на-незалежний-review', 'new_id': 'startup-routing-and-handoff-to-independent-review', 'binding': 'Startup routing and handoff to independent review', 'line': 3}, {'old_id': 'перед-початком-роботи', 'new_id': 'before-starting-work', 'binding': 'Before starting work', 'line': 8}, {'old_id': 'пакет-передачі', 'new_id': 'handoff-package', 'binding': 'Handoff package', 'line': 15}, {'old_id': 'наступна-дія-яку-не-можна-втратити', 'new_id': 'the-next-action-that-must-not-be-lost', 'binding': 'The next action that must not be lost', 'line': 33}, {'old_id': 'delivery-state-та-security-завершення', 'new_id': 'delivery-state-and-security-completion', 'binding': 'Delivery state and security completion', 'line': 63}, {'old_id': 'контракт-reviewer', 'new_id': 'reviewer-contract', 'binding': 'Reviewer contract', 'line': 70}, {'old_id': 'зміни-після-review', 'new_id': 'changes-after-review', 'binding': 'Changes after review', 'line': 77}, {'old_id': 'опційний-stdlib-helper', 'new_id': 'optional-stdlib-helper', 'binding': 'Optional stdlib helper', 'line': 82}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 230, 'end': 230, 'before': '<a id="startup-routing-та-передача-на-незалежний-review"></a>\n', 'after': ''}, {'start': 584, 'end': 584, 'before': '<a id="перед-початком-роботи"></a>\n', 'after': ''}, {'start': 1753, 'end': 1753, 'before': '<a id="пакет-передачі"></a>\n', 'after': ''}, {'start': 3279, 'end': 3279, 'before': '<a id="наступна-дія-яку-не-можна-втратити"></a>\n', 'after': ''}, {'start': 8405, 'end': 8405, 'before': '<a id="delivery-state-та-security-завершення"></a>\n', 'after': ''}, {'start': 9672, 'end': 9672, 'before': '<a id="контракт-reviewer"></a>\n', 'after': ''}, {'start': 10814, 'end': 10814, 'before': '<a id="зміни-після-review"></a>\n', 'after': ''}, {'start': 11477, 'end': 11477, 'before': '<a id="опційний-stdlib-helper"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="startup-routing-та-передача-на-незалежний-review"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="перед-початком-роботи"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="пакет-передачі"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="наступна-дія-яку-не-можна-втратити"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 6, 'record': {'text': '<a id="delivery-state-та-security-завершення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 7, 'record': {'text': '<a id="контракт-reviewer"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 8, 'record': {'text': '<a id="зміни-після-review"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 9, 'record': {'text': '<a id="опційний-stdlib-helper"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '5bc6fe1046604107bff7ddd8d665b4200aef21eea9cece3a6493704857b58edb', 'current_literals_sha256': 'e69e715ebf37ff330d20e094d32980bf5769c3a41728195a2aff20a2cacbf7be'},
    'ai-factory/roadmap.md': {'path': 'ai-factory/roadmap.md', 'pre_anchor_sha256': '72f690b0a4b3a0eb7c7d4d4f24680d1dde8207137cab83784160d1b7e8e1495d', 'current_sha256': 'b3ec939f1e95c21d60c449bd59b9ca8bf43d672f9ddeb6320a2c87f12660b341', 'removed_ids': [{'old_id': 'черга-розвитку-та-критерії-приймання', 'new_id': 'development-queue-and-acceptance-criteria', 'binding': 'Development queue and acceptance criteria', 'line': 10}, {'old_id': '3-авторство-й-оцінювання-скілів', 'new_id': '3-skill-authoring-and-evaluation', 'binding': '3. Skill authoring and evaluation', 'line': 15}, {'old_id': '4-запроєктована-структура-obsidian-для-dg', 'new_id': '4-proposed-obsidian-structure-for-dg', 'binding': '4. Proposed Obsidian structure for dg', 'line': 26}, {'old_id': '5-реєстр-задач-і-критерії-приймання', 'new_id': '5-task-registry-and-acceptance-criteria', 'binding': '5. Task registry and acceptance criteria', 'line': 49}, {'old_id': 'e0--obsidian-для-dg--vault-diagram-hierarchy--p0', 'new_id': 'e0--obsidian-for-dg--vault-diagram-hierarchy--p0', 'binding': 'E0 · Obsidian for dg — vault `diagram-hierarchy`  (P0)', 'line': 57}, {'old_id': 'e1--глобальний-шар-скіли-пайплайна--p0p1', 'new_id': 'e1--global-layer-pipeline-skills--p0p1', 'binding': 'E1 · Global layer: pipeline skills  (P0–P1)', 'line': 74}, {'old_id': 'e2--cargotrans-ui--доростити-наявний-конвеєр--p1', 'new_id': 'e2--cargotrans-ui--extend-the-existing-pipeline--p1', 'binding': 'E2 · cargotrans-ui — extend the existing pipeline  (P1)', 'line': 93}, {'old_id': 'e3--dg--підняти-базу-конвеєра--p1', 'new_id': 'e3--dg--establish-the-pipeline-foundation--p1', 'binding': 'E3 · dg — establish the pipeline foundation  (P1)', 'line': 109}, {'old_id': 'e4--незалежне-ai-ревю-на-pr-p2', 'new_id': 'e4--independent-ai-review-on-prs-p2', 'binding': 'E4 · Independent AI review on PRs (P2)', 'line': 123}, {'old_id': '6-наступний-порядок-після-актуалізації', 'new_id': '6-next-sequence-after-updating-the-inventory', 'binding': '6. Next sequence after updating the inventory', 'line': 143}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 335, 'end': 335, 'before': '<a id="черга-розвитку-та-критерії-приймання"></a>\n', 'after': ''}, {'start': 690, 'end': 690, 'before': '<a id="3-авторство-й-оцінювання-скілів"></a>\n', 'after': ''}, {'start': 1672, 'end': 1672, 'before': '<a id="4-запроєктована-структура-obsidian-для-dg"></a>\n', 'after': ''}, {'start': 2700, 'end': 2700, 'before': '<a id="5-реєстр-задач-і-критерії-приймання"></a>\n', 'after': ''}, {'start': 3010, 'end': 3010, 'before': '<a id="e0--obsidian-для-dg--vault-diagram-hierarchy--p0"></a>\n', 'after': ''}, {'start': 5118, 'end': 5118, 'before': '<a id="e1--глобальний-шар-скіли-пайплайна--p0p1"></a>\n', 'after': ''}, {'start': 9407, 'end': 9407, 'before': '<a id="e2--cargotrans-ui--доростити-наявний-конвеєр--p1"></a>\n', 'after': ''}, {'start': 11280, 'end': 11280, 'before': '<a id="e3--dg--підняти-базу-конвеєра--p1"></a>\n', 'after': ''}, {'start': 12906, 'end': 12906, 'before': '<a id="e4--незалежне-ai-ревю-на-pr-p2"></a>\n', 'after': ''}, {'start': 14367, 'end': 14367, 'before': '<a id="6-наступний-порядок-після-актуалізації"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 1, 'record': {'text': '<a id="черга-розвитку-та-критерії-приймання"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="3-авторство-й-оцінювання-скілів"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="4-запроєктована-структура-obsidian-для-dg"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="5-реєстр-задач-і-критерії-приймання"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="e0--obsidian-для-dg--vault-diagram-hierarchy--p0"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 6, 'record': {'text': '<a id="e1--глобальний-шар-скіли-пайплайна--p0p1"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 7, 'record': {'text': '<a id="e2--cargotrans-ui--доростити-наявний-конвеєр--p1"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 8, 'record': {'text': '<a id="e3--dg--підняти-базу-конвеєра--p1"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 9, 'record': {'text': '<a id="e4--незалежне-ai-ревю-на-pr-p2"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 10, 'record': {'text': '<a id="6-наступний-порядок-після-актуалізації"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'a7dd0d374f9200799c12d5f8d7e7803e691d1f2a365f0c354a1de5112ef104e1', 'current_literals_sha256': 'da9ad97dcd2dbe5f863919c3e2315f342dce03c24a1a5c19f9916a688b2185aa'},
    'ai-factory/status.md': {'path': 'ai-factory/status.md', 'pre_anchor_sha256': '704bf0fcf929b6ea9cb031dadcf65ee6e6a293fd2befedd09e41863462a2fe8d', 'current_sha256': '33c79369248f5934810ed0f55c7f97baa8e6f95fd5760d48ffc5cc02f034a573', 'removed_ids': [{'old_id': 'поточний-статус-можливостей-і-джерела', 'new_id': 'current-capability-status-and-sources', 'binding': 'Current capability status and sources', 'line': 10}, {'old_id': 'переносиме-підключення', 'new_id': 'portable-onboarding', 'binding': 'Portable onboarding', 'line': 27}, {'old_id': 'єдиний-реєстр', 'new_id': 'single-registry', 'binding': 'Single registry', 'line': 32}, {'old_id': 'оновлення-доказів', 'new_id': 'updating-evidence', 'binding': 'Updating evidence', 'line': 59}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 344, 'end': 344, 'before': '<a id="поточний-статус-можливостей-і-джерела"></a>\n', 'after': ''}, {'start': 2401, 'end': 2401, 'before': '<a id="переносиме-підключення"></a>\n', 'after': ''}, {'start': 2792, 'end': 2792, 'before': '<a id="єдиний-реєстр"></a>\n', 'after': ''}, {'start': 9062, 'end': 9062, 'before': '<a id="оновлення-доказів"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 1, 'record': {'text': '<a id="поточний-статус-можливостей-і-джерела"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="переносиме-підключення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="єдиний-реєстр"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="оновлення-доказів"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'fe98951032e81e1e27a5380f3e64641c56ebdfd0a80bbd808eeb4d311a3417a6', 'current_literals_sha256': '432b2a5ec616f09b8db530597ccb3382c3b0be69bdb77ff1a2ef32b5ca7e3c97'},
    'ai-factory/workflow.md': {'path': 'ai-factory/workflow.md', 'pre_anchor_sha256': 'fd6009e489be2defee7804c5b9eb26f86bf2f06102bfe260382be17562999ebb', 'current_sha256': 'af757510334827fde624a18e31194e13d46f170b3c6288c329fa4ae7c3eb52e3', 'removed_ids': [{'old_id': 'task-branch-у-головному-репозиторії', 'new_id': 'task-branch-in-the-main-repository', 'binding': 'Task branch in the main repository', 'line': 10}, {'old_id': 'маршрути-роботи-передача-контексту-та-перевірки', 'new_id': 'work-routes-context-handoff-and-checks', 'binding': 'Work routes, context handoff and checks', 'line': 21}, {'old_id': 'startup-хто-виконує-критику-review-та-перевірки', 'new_id': 'startup-who-performs-critique-review-and-checks', 'binding': 'Startup: who performs critique, review and checks', 'line': 32}, {'old_id': 'вхід-у-проєкт', 'new_id': 'entering-a-project', 'binding': 'Entering a project', 'line': 39}, {'old_id': 'карта-скілів-і-adr', 'new_id': 'skill-and-adr-map', 'binding': 'Skill and ADR map', 'line': 51}, {'old_id': 'вибір-інтервю-та-архітектурної-перевірки', 'new_id': 'selecting-an-interview-and-architecture-check', 'binding': 'Selecting an interview and architecture check', 'line': 56}, {'old_id': 'qualitative-readiness-обовязкові-критерії-та-докази', 'new_id': 'qualitative-readiness-mandatory-criteria-and-evidence', 'binding': 'Qualitative readiness: mandatory criteria and evidence', 'line': 79}, {'old_id': 'джерела-істини', 'new_id': 'sources-of-truth', 'binding': 'Sources of truth', 'line': 124}, {'old_id': 'мінімальна-передача-контексту', 'new_id': 'minimal-context-handoff', 'binding': 'Minimal context handoff', 'line': 135}, {'old_id': 'три-ролі-та-crg', 'new_id': 'three-roles-and-crg', 'binding': 'Three roles and CRG', 'line': 152}, {'old_id': 'виклики-й-доступність-інструментів', 'new_id': 'invocation-and-tool-availability', 'binding': 'Invocation and tool availability', 'line': 159}, {'old_id': 'ui-критерії-готовності', 'new_id': 'ui-readiness-criteria', 'binding': 'UI: readiness criteria', 'line': 169}, {'old_id': 'інтеграція-adr-перевірок-у-наступні-задачі', 'new_id': 'integrating-adr-checks-into-subsequent-tasks', 'binding': 'Integrating ADR checks into subsequent tasks', 'line': 178}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 347, 'end': 347, 'before': '<a id="task-branch-у-головному-репозиторії"></a>\n', 'after': ''}, {'start': 1910, 'end': 1910, 'before': '<a id="маршрути-роботи-передача-контексту-та-перевірки"></a>\n', 'after': ''}, {'start': 2860, 'end': 2860, 'before': '<a id="startup-хто-виконує-критику-review-та-перевірки"></a>\n', 'after': ''}, {'start': 4148, 'end': 4148, 'before': '<a id="вхід-у-проєкт"></a>\n', 'after': ''}, {'start': 5190, 'end': 5190, 'before': '<a id="карта-скілів-і-adr"></a>\n', 'after': ''}, {'start': 5389, 'end': 5389, 'before': '<a id="вибір-інтервю-та-архітектурної-перевірки"></a>\n', 'after': ''}, {'start': 7602, 'end': 7602, 'before': '<a id="qualitative-readiness-обовязкові-критерії-та-докази"></a>\n', 'after': ''}, {'start': 12040, 'end': 12040, 'before': '<a id="джерела-істини"></a>\n', 'after': ''}, {'start': 13794, 'end': 13794, 'before': '<a id="мінімальна-передача-контексту"></a>\n', 'after': ''}, {'start': 15152, 'end': 15152, 'before': '<a id="три-ролі-та-crg"></a>\n', 'after': ''}, {'start': 15779, 'end': 15779, 'before': '<a id="виклики-й-доступність-інструментів"></a>\n', 'after': ''}, {'start': 16426, 'end': 16426, 'before': '<a id="ui-критерії-готовності"></a>\n', 'after': ''}, {'start': 17503, 'end': 17503, 'before': '<a id="інтеграція-adr-перевірок-у-наступні-задачі"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 1, 'record': {'text': '<a id="task-branch-у-головному-репозиторії"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="маршрути-роботи-передача-контексту-та-перевірки"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="startup-хто-виконує-критику-review-та-перевірки"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="вхід-у-проєкт"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 7, 'record': {'text': '<a id="карта-скілів-і-adr"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 8, 'record': {'text': '<a id="вибір-інтервю-та-архітектурної-перевірки"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 9, 'record': {'text': '<a id="qualitative-readiness-обовязкові-критерії-та-докази"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 11, 'record': {'text': '<a id="джерела-істини"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 13, 'record': {'text': '<a id="мінімальна-передача-контексту"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 14, 'record': {'text': '<a id="три-ролі-та-crg"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 15, 'record': {'text': '<a id="виклики-й-доступність-інструментів"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 17, 'record': {'text': '<a id="ui-критерії-готовності"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 18, 'record': {'text': '<a id="інтеграція-adr-перевірок-у-наступні-задачі"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '42c268bd293656c7de1b7646ace13740c3e810a409da2c2513c0708f1d7b44a6', 'current_literals_sha256': '48518ae444da1fdff84145a1b1a501adb863725e18cd81bcbcd6ac3af5a61bcf'},
    'docs/guides/ai-assisted-onboarding.md': {'path': 'docs/guides/ai-assisted-onboarding.md', 'pre_anchor_sha256': 'f3cf9d1b092dfb78ef7bd6f9c2b4cbcfec433588bbc436d39b6d09fb84cfc8cc', 'current_sha256': '74372391dfa0e400ac181360062ea2ee46bd204fcb5f2f5487163184f3a31f80', 'removed_ids': [{'old_id': '1-що-куди-належить', 'new_id': '1-what-belongs-where', 'binding': '1. What belongs where', 'line': 6}, {'old_id': '2-перед-виконанням-і-приватний-доступ', 'new_id': '2-prerequisites-and-private-access', 'binding': '2. Prerequisites and private access', 'line': 23}, {'old_id': '3-реальні-offline-команди', 'new_id': '3-actual-offline-commands', 'binding': '3. Actual offline commands', 'line': 32}, {'old_id': '4-наявний-проєкт--copy-ready-ai-prompt', 'new_id': '4-existing-project--copy-ready-ai-prompt', 'binding': '4. Existing project — copy-ready AI prompt', 'line': 66}, {'old_id': '5-порожній-проєкт--copy-ready-ai-prompt', 'new_id': '5-empty-project--copy-ready-ai-prompt', 'binding': '5. Empty project — copy-ready AI prompt', 'line': 91}, {'old_id': '6-новий-developer--машина--copy-ready-ai-prompt', 'new_id': '6-new-developer--machine--copy-ready-ai-prompt', 'binding': '6. New developer / machine — copy-ready AI prompt', 'line': 113}, {'old_id': '7-update-backups-rollback-і-межі-uninstall', 'new_id': '7-update-backups-rollback-and-uninstall-boundaries', 'binding': '7. Update, backups, rollback and uninstall boundaries', 'line': 137}, {'old_id': '8-як-перевірити-готовність', 'new_id': '8-how-to-verify-readiness', 'binding': '8. How to verify readiness', 'line': 151}, {'old_id': '9-security-adoption--proposed-не-installed', 'new_id': '9-security-adoption--proposed-not-installed', 'binding': '9. Security adoption — PROPOSED, not installed', 'line': 168}, {'old_id': 'risk-triggered-gates-у-чинному-lifecycle', 'new_id': 'risk-triggered-gates-in-the-current-lifecycle', 'binding': 'Risk-triggered gates in the current lifecycle', 'line': 180}, {'old_id': 'scanner-gate-потребує-власної-перевірки', 'new_id': 'the-scanner-gate-needs-its-own-verification', 'binding': 'The scanner gate needs its own verification', 'line': 196}, {'old_id': 'final-evidence-та-межі-заяв-про-завершення', 'new_id': 'final-evidence-and-boundaries-of-completion-claims', 'binding': 'Final evidence and boundaries of completion claims', 'line': 201}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 381, 'end': 381, 'before': '<a id="1-що-куди-належить"></a>\n', 'after': ''}, {'start': 3163, 'end': 3163, 'before': '<a id="2-перед-виконанням-і-приватний-доступ"></a>\n', 'after': ''}, {'start': 4724, 'end': 4724, 'before': '<a id="3-реальні-offline-команди"></a>\n', 'after': ''}, {'start': 7994, 'end': 7994, 'before': '<a id="4-наявний-проєкт--copy-ready-ai-prompt"></a>\n', 'after': ''}, {'start': 9735, 'end': 9735, 'before': '<a id="5-порожній-проєкт--copy-ready-ai-prompt"></a>\n', 'after': ''}, {'start': 11653, 'end': 11653, 'before': '<a id="6-новий-developer--машина--copy-ready-ai-prompt"></a>\n', 'after': ''}, {'start': 13739, 'end': 13739, 'before': '<a id="7-update-backups-rollback-і-межі-uninstall"></a>\n', 'after': ''}, {'start': 15422, 'end': 15422, 'before': '<a id="8-як-перевірити-готовність"></a>\n', 'after': ''}, {'start': 17585, 'end': 17585, 'before': '<a id="9-security-adoption--proposed-не-installed"></a>\n', 'after': ''}, {'start': 19809, 'end': 19809, 'before': '<a id="risk-triggered-gates-у-чинному-lifecycle"></a>\n', 'after': ''}, {'start': 23992, 'end': 23992, 'before': '<a id="scanner-gate-потребує-власної-перевірки"></a>\n', 'after': ''}, {'start': 24898, 'end': 24898, 'before': '<a id="final-evidence-та-межі-заяв-про-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 1, 'record': {'text': '<a id="1-що-куди-належить"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="2-перед-виконанням-і-приватний-доступ"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="3-реальні-offline-команди"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="4-наявний-проєкт--copy-ready-ai-prompt"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 7, 'record': {'text': '<a id="5-порожній-проєкт--copy-ready-ai-prompt"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 9, 'record': {'text': '<a id="6-новий-developer--машина--copy-ready-ai-prompt"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 10, 'record': {'text': '<a id="7-update-backups-rollback-і-межі-uninstall"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 11, 'record': {'text': '<a id="8-як-перевірити-готовність"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 13, 'record': {'text': '<a id="9-security-adoption--proposed-не-installed"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 14, 'record': {'text': '<a id="risk-triggered-gates-у-чинному-lifecycle"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 15, 'record': {'text': '<a id="scanner-gate-потребує-власної-перевірки"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 16, 'record': {'text': '<a id="final-evidence-та-межі-заяв-про-завершення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '293b2fcd1d8cdd7ff40f019acc6f338709ac29ae50a7e4274fda1a62bc66db5f', 'current_literals_sha256': '22cfc71b6100a6100f3facee0c571418f8bee2153b3b5ff63af2caeb0670d6c6'},
    'docs/portable/change-protocol.md': {'path': 'docs/portable/change-protocol.md', 'pre_anchor_sha256': 'be618bb3a2e4e506e3eff994ab6458bfd375167e03a6fd6ea74e6f065018ada7', 'current_sha256': '344eb75d74942345c1d002df60c5f8b4339a66f76d23d6423abf6fc44528f345', 'removed_ids': [{'old_id': 'additive-зміна-повтор-і-guarded-restore', 'new_id': 'additive-change-repeat-and-guarded-restore', 'binding': 'Additive change, repeat and guarded restore', 'line': 3}, {'old_id': 'перед-записом', 'new_id': 'before-writing', 'binding': 'Before writing', 'line': 10}, {'old_id': 'restore-лише-власного-застосованого-diff', 'new_id': 'restore-only-your-own-applied-diff', 'binding': 'Restore only your own applied diff', 'line': 19}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 174, 'end': 174, 'before': '<a id="additive-зміна-повтор-і-guarded-restore"></a>\n', 'after': ''}, {'start': 575, 'end': 575, 'before': '<a id="перед-записом"></a>\n', 'after': ''}, {'start': 2224, 'end': 2224, 'before': '<a id="restore-лише-власного-застосованого-diff"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="additive-зміна-повтор-і-guarded-restore"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="перед-записом"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="restore-лише-власного-застосованого-diff"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '58c28befefe5131c800e9b37c4c0581c9a4a8aa6a593a166801632abd99de3a5', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'docs/portable/crg.md': {'path': 'docs/portable/crg.md', 'pre_anchor_sha256': '6ab7f78d565a3473889d5a888df8fa72347983f18610e025138916119d7156ed', 'current_sha256': 'afab282b6ed0b5f5088b97830b50f795527e907aebd307a0d1333c30087989e4', 'removed_ids': [{'old_id': 'freshness-перед-довірою', 'new_id': 'freshness-before-trust', 'binding': 'Freshness before trust', 'line': 7}, {'old_id': 'відновлення-без-зміни-source', 'new_id': 'recovery-without-source-changes', 'binding': 'Recovery without source changes', 'line': 17}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 557, 'end': 557, 'before': '<a id="freshness-перед-довірою"></a>\n', 'after': ''}, {'start': 1936, 'end': 1936, 'before': '<a id="відновлення-без-зміни-source"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="freshness-перед-довірою"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="відновлення-без-зміни-source"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '7d4c9346a0dbe3f4a22916117908b8339e39a0deac23b5732f56c6314d5d00d8', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'docs/portable/models.md': {'path': 'docs/portable/models.md', 'pre_anchor_sha256': '11ec1e94958c4636aacf9d8efe4e140342243f1445e7e926783747e68a22ce93', 'current_sha256': '1cdcad891d19be127b9bcc1c6961d294ab663f2dde3a7c8ad7bcb7318043e6db', 'removed_ids': [{'old_id': 'bindings-і-рівень-підтвердження', 'new_id': 'bindings-and-confirmation-level', 'binding': 'Bindings and confirmation level', 'line': 18}, {'old_id': 'ліміти-роботи', 'new_id': 'work-limits', 'binding': 'Work limits', 'line': 36}, {'old_id': 'crg-і-мінімальний-handoff', 'new_id': 'crg-and-minimum-handoff', 'binding': 'CRG and minimum handoff', 'line': 45}, {'old_id': 'докази-доступності', 'new_id': 'availability-evidence', 'binding': 'Availability evidence', 'line': 52}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 1584, 'end': 1584, 'before': '<a id="bindings-і-рівень-підтвердження"></a>\n', 'after': ''}, {'start': 3894, 'end': 3894, 'before': '<a id="ліміти-роботи"></a>\n', 'after': ''}, {'start': 4905, 'end': 4905, 'before': '<a id="crg-і-мінімальний-handoff"></a>\n', 'after': ''}, {'start': 5621, 'end': 5621, 'before': '<a id="докази-доступності"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="bindings-і-рівень-підтвердження"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="ліміти-роботи"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="crg-і-мінімальний-handoff"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="докази-доступності"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'bc9a1b3b31391f5353d5e36d95af9f32678a17cc66827bf39e119ff228bd9a76', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'docs/portable/review-handoff.md': {'path': 'docs/portable/review-handoff.md', 'pre_anchor_sha256': '67f49dc9f57a1421713ab096d983d28c4b78fc4df19952704ff44a9c7ce4a077', 'current_sha256': '2a5a2ba6b0eeaada9da34d47aaae08516964bd762e43728ceb34688441090c6a', 'removed_ids': [{'old_id': 'startup-routing-та-передача-на-незалежний-review', 'new_id': 'startup-routing-and-handoff-to-independent-review', 'binding': 'Startup routing and handoff to independent review', 'line': 3}, {'old_id': 'перед-початком-роботи', 'new_id': 'before-starting-work', 'binding': 'Before starting work', 'line': 8}, {'old_id': 'пакет-передачі', 'new_id': 'handoff-package', 'binding': 'Handoff package', 'line': 19}, {'old_id': 'контракт-reviewer', 'new_id': 'reviewer-contract', 'binding': 'Reviewer contract', 'line': 34}, {'old_id': 'зміни-після-review', 'new_id': 'changes-after-review', 'binding': 'Changes after review', 'line': 41}, {'old_id': 'опційний-stdlib-helper', 'new_id': 'optional-stdlib-helper', 'binding': 'Optional stdlib helper', 'line': 46}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 174, 'end': 174, 'before': '<a id="startup-routing-та-передача-на-незалежний-review"></a>\n', 'after': ''}, {'start': 541, 'end': 541, 'before': '<a id="перед-початком-роботи"></a>\n', 'after': ''}, {'start': 2030, 'end': 2030, 'before': '<a id="пакет-передачі"></a>\n', 'after': ''}, {'start': 3354, 'end': 3354, 'before': '<a id="контракт-reviewer"></a>\n', 'after': ''}, {'start': 4521, 'end': 4521, 'before': '<a id="зміни-після-review"></a>\n', 'after': ''}, {'start': 5179, 'end': 5179, 'before': '<a id="опційний-stdlib-helper"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="startup-routing-та-передача-на-незалежний-review"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="перед-початком-роботи"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="пакет-передачі"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="контракт-reviewer"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="зміни-після-review"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="опційний-stdlib-helper"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '1f5b6431972a08c30a9b353a59cf70aae83d6ffb8d0054bdb794f14c135e11bb', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'rules/README.md': {'path': 'rules/README.md', 'pre_anchor_sha256': '97460996a0534546208b48ae8951a75f9f0ca22bb46b0efd445c0c6d79b34129', 'current_sha256': '934bed423df7cc3ccb9ce49312e152e33e50a62b4d53f261c2bfd26df3541948', 'removed_ids': [{'old_id': 'доступ-з-obsidian', 'new_id': 'access-from-obsidian', 'binding': 'Access from Obsidian', 'line': 12}, {'old_id': 'файли', 'new_id': 'files', 'binding': 'Files', 'line': 19}, {'old_id': 'як-правило-доходить-до-застосування', 'new_id': 'how-a-rule-reaches-execution', 'binding': 'How a rule reaches execution', 'line': 37}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 616, 'end': 616, 'before': '<a id="доступ-з-obsidian"></a>\n', 'after': ''}, {'start': 931, 'end': 931, 'before': '<a id="файли"></a>\n', 'after': ''}, {'start': 2133, 'end': 2133, 'before': '<a id="як-правило-доходить-до-застосування"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="доступ-з-obsidian"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="файли"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="як-правило-доходить-до-застосування"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '15cc34953035af543710093c9cc286d66718b10a438da0a2b902bd66619a0aff', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'rules/agent-entry.md': {'path': 'rules/agent-entry.md', 'pre_anchor_sha256': '5b1a772fbdc6fe04e1e5307ec1096b04f1caf54e35ce2edca7cca088f0091933', 'current_sha256': '8fba1330a804e830e7ee6c25f6043be8d7f928dd72624f99883134d607376975', 'removed_ids': [{'old_id': 'agentsmd--точка-входу-до-agents', 'new_id': 'agentsmd--entry-point-for-agents', 'binding': 'AGENTS.md — entry point for `~/.agents`', 'line': 1}, {'old_id': 'що-де-лежить', 'new_id': 'where-things-live', 'binding': 'Where things live', 'line': 13}, {'old_id': '-правила-які-мусять-спрацювати-до-завантаження-будь-якого-скіла', 'new_id': '-rules-that-must-take-effect-before-loading-any-skill', 'binding': '🔴 Rules that must take effect **before** loading any skill', 'line': 27}, {'old_id': '1-сабагент-пише-хід-у-власний-файл', 'new_id': '1-a-subagent-writes-progress-to-its-own-file', 'binding': '1. A subagent writes progress to its own file', 'line': 34}, {'old_id': '2-мовчазний-агент--не-чистий-агент', 'new_id': '2-a-silent-agent-is-not-a-clean-agent', 'binding': '2. A silent agent is not a clean agent', 'line': 56}, {'old_id': 'як-додавати-правило', 'new_id': 'how-to-add-a-rule', 'binding': 'How to add a rule', 'line': 66}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="agentsmd--точка-входу-до-agents"></a>\n', 'after': ''}, {'start': 424, 'end': 424, 'before': '<a id="що-де-лежить"></a>\n', 'after': ''}, {'start': 1016, 'end': 1016, 'before': '<a id="-правила-які-мусять-спрацювати-до-завантаження-будь-якого-скіла"></a>\n', 'after': ''}, {'start': 1271, 'end': 1271, 'before': '<a id="1-сабагент-пише-хід-у-власний-файл"></a>\n', 'after': ''}, {'start': 2312, 'end': 2312, 'before': '<a id="2-мовчазний-агент--не-чистий-агент"></a>\n', 'after': ''}, {'start': 2675, 'end': 2675, 'before': '<a id="як-додавати-правило"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="agentsmd--точка-входу-до-agents"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="що-де-лежить"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="-правила-які-мусять-спрацювати-до-завантаження-будь-якого-скіла"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="1-сабагент-пише-хід-у-власний-файл"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="2-мовчазний-агент--не-чистий-агент"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="як-додавати-правило"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '434a42f03c074ae4cc394374b62a6066182797907824d6d180d348e87434f618', 'current_literals_sha256': '2d90338f7147bfa248decf147742444d340baf9418191bfb8d5cd10307ce4390'},
    'rules/subagent-orchestration-ledger.md': {'path': 'rules/subagent-orchestration-ledger.md', 'pre_anchor_sha256': '09dcbdfdb2e3ab783ce2dc2a7906eecc018ac64ec623218a786233b418f66cd8', 'current_sha256': '03626da3bc9480b4a51c5837bba1c675366f408de23e6a685ef66f9bedba0af2', 'removed_ids': [{'old_id': '-subagent-orchestration-ledger-4-статуси-brief-файли', 'new_id': '-subagent-orchestration-ledger-4-statuses-brief-files', 'binding': '🧩 Subagent-orchestration: ledger, 4 statuses, brief files', 'line': 5}, {'old_id': 'коли-застосовувати', 'new_id': 'when-to-apply', 'binding': 'When to apply', 'line': 15}, {'old_id': '1-durable-ledger-progress-файл', 'new_id': '1-durable-ledger-progress-file', 'binding': '1. Durable ledger (progress file)', 'line': 23}, {'old_id': '2-статус-протокол-implementerа-4-коди--реакція-controllerа', 'new_id': '2-implementer-status-protocol-4-codes--controller-response', 'binding': '2. Implementer status protocol (4 codes → controller response)', 'line': 49}, {'old_id': '3-brief-file-handoff-артефакти-як-файли-не-інлайн-текст', 'new_id': '3-brief-file-handoff-artifacts-as-files-not-inline-text', 'binding': '3. Brief-file handoff (artifacts as files, not inline text)', 'line': 64}, {'old_id': 'антипатерни', 'new_id': 'antipatterns', 'binding': 'Antipatterns', 'line': 81}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 87, 'end': 87, 'before': '<a id="-subagent-orchestration-ledger-4-статуси-brief-файли"></a>\n', 'after': ''}, {'start': 1074, 'end': 1074, 'before': '<a id="коли-застосовувати"></a>\n', 'after': ''}, {'start': 1346, 'end': 1346, 'before': '<a id="1-durable-ledger-progress-файл"></a>\n', 'after': ''}, {'start': 2810, 'end': 2810, 'before': '<a id="2-статус-протокол-implementerа-4-коди--реакція-controllerа"></a>\n', 'after': ''}, {'start': 3645, 'end': 3645, 'before': '<a id="3-brief-file-handoff-артефакти-як-файли-не-інлайн-текст"></a>\n', 'after': ''}, {'start': 4480, 'end': 4480, 'before': '<a id="антипатерни"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="-subagent-orchestration-ledger-4-статуси-brief-файли"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="коли-застосовувати"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="1-durable-ledger-progress-файл"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 3, 'record': {'text': '<a id="2-статус-протокол-implementerа-4-коди--реакція-controllerа"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 4, 'record': {'text': '<a id="3-brief-file-handoff-артефакти-як-файли-не-інлайн-текст"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 5, 'record': {'text': '<a id="антипатерни"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'c9625c5404af68b7d77c7e589ff30e8da9d6a0bb86f0d170acb3cded4f6e1f09', 'current_literals_sha256': 'd6594b632249e1c4fce5058b0113768f2ec0194c291028a0bbd9fc692535371d'},
    'templates/acceptance-full.md': {'path': 'templates/acceptance-full.md', 'pre_anchor_sha256': '6e3a5ee9a70cf0c67523a67ccf615abbca105165465032754661f4b5470dbc12', 'current_sha256': 'a1dbde842e097aa064d009a1bf098a4781f2abf1fa3bbef980b891b7f4136209', 'removed_ids': [{'old_id': 'acceptance-підключення-ai-factory', 'new_id': 'ai-factory-integration-acceptance', 'binding': 'AI Factory integration acceptance', 'line': 1}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="acceptance-підключення-ai-factory"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="acceptance-підключення-ai-factory"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '53955bb9a8bc7f2313f65c6d7322adf41590daa49a0e28db1f0a3f04446f144e', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'templates/acceptance-portable.md': {'path': 'templates/acceptance-portable.md', 'pre_anchor_sha256': '46ee360c0b6f90f737eaf27da64b278930a33095d4feba162f42543ec2a316ad', 'current_sha256': 'cccc30779fceabf0e1d17bd15d56ee94901e890613882c70eba952e44d707291', 'removed_ids': [{'old_id': 'acceptance-підключення-ai-factory', 'new_id': 'ai-factory-integration-acceptance', 'binding': 'AI Factory integration acceptance', 'line': 1}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="acceptance-підключення-ai-factory"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="acceptance-підключення-ai-factory"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': '53955bb9a8bc7f2313f65c6d7322adf41590daa49a0e28db1f0a3f04446f144e', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'templates/adapter-full.md': {'path': 'templates/adapter-full.md', 'pre_anchor_sha256': '7f65a5e3130bfc0642392b4f59443ba40cbd66326bd4313493f08dde5e63f4a3', 'current_sha256': 'd749a70679bf1119cb9b3faa4823f2e5e9190dc7d17a3ca5f8180e1b84a38bb3', 'removed_ids': [{'old_id': 'ai-factory--адаптер-наявного-workflow', 'new_id': 'ai-factory--existing-workflow-adapter', 'binding': 'AI Factory — existing workflow adapter', 'line': 1}, {'old_id': 'migration--рішення', 'new_id': 'migration--decisions', 'binding': 'Migration / decisions', 'line': 35}, {'old_id': 'приймання-підключення', 'new_id': 'integration-acceptance', 'binding': 'Integration acceptance', 'line': 47}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="ai-factory--адаптер-наявного-workflow"></a>\n', 'after': ''}, {'start': 3505, 'end': 3505, 'before': '<a id="migration--рішення"></a>\n', 'after': ''}, {'start': 4358, 'end': 4358, 'before': '<a id="приймання-підключення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="ai-factory--адаптер-наявного-workflow"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 1, 'record': {'text': '<a id="migration--рішення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}, {'index': 2, 'record': {'text': '<a id="приймання-підключення"></a>', 'reason': 'Original heading fragment retained as an explicit compatibility anchor.'}}], 'pre_literals_sha256': 'a3ee21cc7e8408fb705c526e8212d6c27646ca06dc9ddeb1a765ca122da2578b', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'docs/translations/en/ai-factory/history.md': {'path': 'docs/translations/en/ai-factory/history.md', 'pre_anchor_sha256': '97e66312892034c2a77d380a24205a303cc328e039117910d20d3f895a557040', 'current_sha256': '61facbcfb7b811d2951de8d1a59d64ccdea2a9fede9e3be289cda960c980655b', 'removed_ids': [{'old_id': 'історія-задуму-та-попередніх-вимірів', 'new_id': 'history-of-the-concept-and-previous-measurements', 'binding': 'History of the concept and previous measurements', 'line': 12}, {'old_id': '1-історичний-розбір-треду-2026-08-25', 'new_id': '1-historical-analysis-of-the-thread-2026-08-25', 'binding': '1. Historical analysis of the thread (2026-08-25)', 'line': 17}, {'old_id': '11-deep-cto-research-перед-кодом', 'new_id': '11-deep-cto-research-before-code', 'binding': '1.1 Deep CTO research before code', 'line': 24}, {'old_id': '12-план-як-детальний-документ-75-часу', 'new_id': '12-the-plan-as-a-detailed-document-75-of-the-time', 'binding': '1.2 The plan as a detailed document (75% of the time)', 'line': 37}, {'old_id': '13-план-критикує-сам-себе-ai-slop-дірки-зайва-складність-edge-cases', 'new_id': '13-the-plan-critiques-itself-ai-slop-gaps-excess-complexity-edge-cases', 'binding': '1.3 The plan critiques itself (AI-slop, gaps, excess complexity, edge cases)', 'line': 46}, {'old_id': '14-різні-моделі-для-різних-ролей', 'new_id': '14-different-models-for-different-roles', 'binding': '1.4 Different models for different roles', 'line': 54}, {'old_id': '15-плани-захищають-перед-імплементацією', 'new_id': '15-plans-are-defended-before-implementation', 'binding': '1.5 Plans are defended before implementation', 'line': 58}, {'old_id': '16-ai-cto-ріже-роботу-на-команди-та-спринти', 'new_id': '16-ai-cto-splits-work-into-teams-and-sprints', 'binding': '1.6 AI CTO splits work into teams and sprints', 'line': 68}, {'old_id': '17-тести-плануються-до-коду-детерміністично-на-рівні-продукту', 'new_id': '17-tests-are-planned-before-code-deterministically-at-product-level', 'binding': '1.7 Tests are planned before code, deterministically, at product level', 'line': 76}, {'old_id': '18-тестове-середовище-як-prod-агент-проходить-фічу-як-юзер-контрольований-доступ-до-логівсервісівread-only-бд-дії-трекаються', 'new_id': '18-a-prod-like-test-environment-the-agent-walks-through-the-feature-as-a-user-controlled-access-to-logsservicesread-only-databases-actions-are-tracked', 'binding': '1.8 A prod-like test environment; the agent walks through the feature as a user; controlled access to logs/services/read-only databases; actions are tracked', 'line': 86}, {'old_id': '19-execution-550-паралельних-pr', 'new_id': '19-execution-550-parallel-prs', 'binding': '1.9 Execution: 5–50 parallel PRs', 'line': 95}, {'old_id': '110-незалежні-ai-ревюєри-на-github-ревюєр-не-знає-як-писався-код', 'new_id': '110-independent-ai-reviewers-on-github-the-reviewer-does-not-know-how-the-code-was-written', 'binding': '1.10 Independent AI reviewers on GitHub; the reviewer does not know how the code was written', 'line': 104}, {'old_id': '111-звіт-замість-полотна-що-зроблено-які-сценарії-протестовані-що-неочевидного-знайшли-скріни-проходка-по-flow-ризики', 'new_id': '111-a-report-instead-of-a-wall-of-text-what-was-done-scenarios-tested-non-obvious-findings-screenshots-flow-walkthrough-risks', 'binding': '1.11 A report instead of a wall of text: what was done, scenarios tested, non-obvious findings, screenshots, flow walkthrough, risks', 'line': 112}, {'old_id': '112-post-deploy-ключові-тести-на-prod-логи-інтеграції-фінальний-апдейт', 'new_id': '112-post-deploy-key-tests-on-prod-logs-integrations-final-update', 'binding': '1.12 Post-deploy: key tests on prod, logs, integrations, final update', 'line': 119}, {'old_id': '2-reality-check-по-треду-принципи-не-метрики', 'new_id': '2-reality-check-of-the-thread-principles-not-metrics', 'binding': '2. Reality-check of the thread (principles, not metrics)', 'line': 126}, {'old_id': '51-історичний-запис-виміру-2026-08-25', 'new_id': '51-historical-measurement-record-2026-08-25', 'binding': '5.1 Historical measurement record (2026-08-25)', 'line': 139}, {'old_id': 'що-показав-бойовий-прогін--і-чого-в-плані-немає', 'new_id': 'what-the-real-world-run-revealed--and-what-the-plan-lacks', 'binding': 'What the real-world run revealed — and what the plan lacks', 'line': 159}, {'old_id': 'історичні-записи-e4e5-з-попереднього-реєстру', 'new_id': 'historical-e4e5-records-from-the-previous-registry', 'binding': 'Historical E4/E5 records from the previous registry', 'line': 191}, {'old_id': 'e4--незалежне-ai-ревю-на-pr--p2', 'new_id': 'e4--independent-ai-review-on-prs--p2', 'binding': 'E4 · Independent AI review on PRs  (P2)', 'line': 194}], 'changed_targets': [], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [], 'hunks': [{'start': 547, 'end': 693, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 1043, 'end': 1043, 'before': '<a id="історія-задуму-та-попередніх-вимірів"></a>\n', 'after': ''}, {'start': 1389, 'end': 1389, 'before': '<a id="1-історичний-розбір-треду-2026-08-25"></a>\n', 'after': ''}, {'start': 1696, 'end': 1696, 'before': '<a id="11-deep-cto-research-перед-кодом"></a>\n', 'after': ''}, {'start': 2561, 'end': 2561, 'before': '<a id="12-план-як-детальний-документ-75-часу"></a>\n', 'after': ''}, {'start': 3066, 'end': 3066, 'before': '<a id="13-план-критикує-сам-себе-ai-slop-дірки-зайва-складність-edge-cases"></a>\n', 'after': ''}, {'start': 3651, 'end': 3651, 'before': '<a id="14-різні-моделі-для-різних-ролей"></a>\n', 'after': ''}, {'start': 4108, 'end': 4108, 'before': '<a id="15-плани-захищають-перед-імплементацією"></a>\n', 'after': ''}, {'start': 4743, 'end': 4743, 'before': '<a id="16-ai-cto-ріже-роботу-на-команди-та-спринти"></a>\n', 'after': ''}, {'start': 5262, 'end': 5262, 'before': '<a id="17-тести-плануються-до-коду-детерміністично-на-рівні-продукту"></a>\n', 'after': ''}, {'start': 5839, 'end': 5839, 'before': '<a id="18-тестове-середовище-як-prod-агент-проходить-фічу-як-юзер-контрольований-доступ-до-логівсервісівread-only-бд-дії-трекаються"></a>\n', 'after': ''}, {'start': 6577, 'end': 6577, 'before': '<a id="19-execution-550-паралельних-pr"></a>\n', 'after': ''}, {'start': 7159, 'end': 7159, 'before': '<a id="110-незалежні-ai-ревюєри-на-github-ревюєр-не-знає-як-писався-код"></a>\n', 'after': ''}, {'start': 7834, 'end': 7834, 'before': '<a id="111-звіт-замість-полотна-що-зроблено-які-сценарії-протестовані-що-неочевидного-знайшли-скріни-проходка-по-flow-ризики"></a>\n', 'after': ''}, {'start': 8395, 'end': 8395, 'before': '<a id="112-post-deploy-ключові-тести-на-prod-логи-інтеграції-фінальний-апдейт"></a>\n', 'after': ''}, {'start': 8689, 'end': 8689, 'before': '<a id="2-reality-check-по-треду-принципи-не-метрики"></a>\n', 'after': ''}, {'start': 9461, 'end': 9461, 'before': '<a id="51-історичний-запис-виміру-2026-08-25"></a>\n', 'after': ''}, {'start': 10792, 'end': 10792, 'before': '<a id="що-показав-бойовий-прогін--і-чого-в-плані-немає"></a>\n', 'after': ''}, {'start': 12693, 'end': 12693, 'before': '<a id="історичні-записи-e4e5-з-попереднього-реєстру"></a>\n', 'after': ''}, {'start': 12749, 'end': 12749, 'before': '<a id="e4--незалежне-ai-ревю-на-pr--p2"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="історія-задуму-та-попередніх-вимірів"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 1, 'record': {'text': '<a id="1-історичний-розбір-треду-2026-08-25"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 2, 'record': {'text': '<a id="11-deep-cto-research-перед-кодом"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 3, 'record': {'text': '<a id="12-план-як-детальний-документ-75-часу"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 4, 'record': {'text': '<a id="13-план-критикує-сам-себе-ai-slop-дірки-зайва-складність-edge-cases"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 5, 'record': {'text': '<a id="14-різні-моделі-для-різних-ролей"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 6, 'record': {'text': '<a id="15-плани-захищають-перед-імплементацією"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 7, 'record': {'text': '<a id="16-ai-cto-ріже-роботу-на-команди-та-спринти"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 8, 'record': {'text': '<a id="17-тести-плануються-до-коду-детерміністично-на-рівні-продукту"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 9, 'record': {'text': '<a id="18-тестове-середовище-як-prod-агент-проходить-фічу-як-юзер-контрольований-доступ-до-логівсервісівread-only-бд-дії-трекаються"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 10, 'record': {'text': '<a id="19-execution-550-паралельних-pr"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 11, 'record': {'text': '<a id="110-незалежні-ai-ревюєри-на-github-ревюєр-не-знає-як-писався-код"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 12, 'record': {'text': '<a id="111-звіт-замість-полотна-що-зроблено-які-сценарії-протестовані-що-неочевидного-знайшли-скріни-проходка-по-flow-ризики"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 13, 'record': {'text': '<a id="112-post-deploy-ключові-тести-на-prod-логи-інтеграції-фінальний-апдейт"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 14, 'record': {'text': '<a id="2-reality-check-по-треду-принципи-не-метрики"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 15, 'record': {'text': '<a id="51-історичний-запис-виміру-2026-08-25"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 16, 'record': {'text': '<a id="що-показав-бойовий-прогін--і-чого-в-плані-немає"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 17, 'record': {'text': '<a id="історичні-записи-e4e5-з-попереднього-реєстру"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 18, 'record': {'text': '<a id="e4--незалежне-ai-ревю-на-pr--p2"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}], 'pre_literals_sha256': 'de73d1b6e44bb507c3fdcd1090a42d8b67365411066d541f9338dfc8d3b30248', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'docs/translations/en/ai-factory/repo-evidence.md': {'path': 'docs/translations/en/ai-factory/repo-evidence.md', 'pre_anchor_sha256': '1ddebf9c43144e99b3c97f686f41436e1b12ae573f2b0782b9d9237b952a1971', 'current_sha256': '9b4967f8758456fe3bde9753a622740cde7d93029c605d427d84233108b50bfa', 'removed_ids': [{'old_id': 'adr-і-workflow-джерела-qna-та-generic-ui', 'new_id': 'adr-and-workflow-qna-and-generic-ui-sources', 'binding': 'ADR and workflow: QnA and generic-ui sources', 'line': 12}, {'old_id': '71-джерела-й-межі-висновку', 'new_id': '71-sources-and-limits-of-the-conclusion', 'binding': '7.1 Sources and limits of the conclusion', 'line': 15}, {'old_id': '72-коли-потрібен-adr-а-коли-достатньо-іншого-запису', 'new_id': '72-when-an-adr-is-needed-and-when-another-record-suffices', 'binding': '7.2 When an ADR is needed and when another record suffices', 'line': 27}, {'old_id': '73-хто-запускає-етапи-і-як-повязані-артефакти', 'new_id': '73-who-initiates-stages-and-how-artifacts-relate', 'binding': '7.3 Who initiates stages and how artifacts relate', 'line': 40}, {'old_id': '74-які-скіли-справді-підключені', 'new_id': '74-which-skills-are-actually-connected', 'binding': '7.4 Which skills are actually connected', 'line': 59}, {'old_id': '75-приклади-й-виявлені-розбіжності', 'new_id': '75-examples-and-identified-discrepancies', 'binding': '7.5 Examples and identified discrepancies', 'line': 78}], 'changed_targets': [], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [], 'hunks': [{'start': 664, 'end': 810, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 1160, 'end': 1160, 'before': '<a id="adr-і-workflow-джерела-qna-та-generic-ui"></a>\n', 'after': ''}, {'start': 1208, 'end': 1208, 'before': '<a id="71-джерела-й-межі-висновку"></a>\n', 'after': ''}, {'start': 1973, 'end': 1973, 'before': '<a id="72-коли-потрібен-adr-а-коли-достатньо-іншого-запису"></a>\n', 'after': ''}, {'start': 3693, 'end': 3693, 'before': '<a id="73-хто-запускає-етапи-і-як-повязані-артефакти"></a>\n', 'after': ''}, {'start': 6057, 'end': 6057, 'before': '<a id="74-які-скіли-справді-підключені"></a>\n', 'after': ''}, {'start': 7930, 'end': 7930, 'before': '<a id="75-приклади-й-виявлені-розбіжності"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="adr-і-workflow-джерела-qna-та-generic-ui"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 1, 'record': {'text': '<a id="71-джерела-й-межі-висновку"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 2, 'record': {'text': '<a id="72-коли-потрібен-adr-а-коли-достатньо-іншого-запису"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 3, 'record': {'text': '<a id="73-хто-запускає-етапи-і-як-повязані-артефакти"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 4, 'record': {'text': '<a id="74-які-скіли-справді-підключені"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 5, 'record': {'text': '<a id="75-приклади-й-виявлені-розбіжності"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}], 'pre_literals_sha256': '226eb375d69f3c0c24f010143ec5ffe439fec3cdf737e294a607161d536b4c98', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'docs/translations/en/docs/guides/obsidian-cheatsheet.md': {'path': 'docs/translations/en/docs/guides/obsidian-cheatsheet.md', 'pre_anchor_sha256': '663bcff5e0b9cc0a458d0173caa4c7ab35900fd0993db3ca7f62f9977f459f0c', 'current_sha256': 'ba6b9ec132055fd60a82cfa3c6d1621163afd9d4e5dd751199311128f8539035', 'removed_ids': [{'old_id': '0-ключові-принципи-чому-саме-так', 'new_id': '0-key-principles-why-this-design', 'binding': '0. Key principles (why this design)', 'line': 17}, {'old_id': '1-розкладка-на-диску', 'new_id': '1-disk-layout', 'binding': '1. Disk layout', 'line': 30}, {'old_id': '2-створення-структури--symlink-глобальної-зони', 'new_id': '2-create-the-structure--symlink-the-global-area', 'binding': '2. Create the structure + symlink the global area', 'line': 54}, {'old_id': 'нюанс-з-obsidian', 'new_id': 'the-obsidian-detail', 'binding': 'The `.obsidian` detail', 'line': 68}, {'old_id': 'бекап-без-хмари', 'new_id': 'backup-without-the-cloud', 'binding': 'Backup without the cloud', 'line': 83}, {'old_id': '3-obsidian-mcp--по-порту-на-кожен-project-vault', 'new_id': '3-obsidian-mcp--one-port-per-project-vault', 'binding': '3. Obsidian MCP — one port per project vault', 'line': 93}, {'old_id': '4-привязка-до-claude-code-scope-на-репо', 'new_id': '4-bind-to-claude-code-repository-scope', 'binding': '4. Bind to Claude Code (repository scope)', 'line': 118}, {'old_id': '5-code-review-graph--окремий-граф-на-репо', 'new_id': '5-code-review-graph--a-separate-graph-per-repository', 'binding': '5. code-review-graph — a separate graph per repository', 'line': 154}, {'old_id': '6-підсумкова-карта', 'new_id': '6-summary-map', 'binding': '6. Summary map', 'line': 187}, {'old_id': '7-чек-ліст-запуску-нового-проєкту', 'new_id': '7-new-project-startup-checklist', 'binding': '7. New-project startup checklist', 'line': 202}, {'old_id': '8-відкриті-опції-не-реалізовано', 'new_id': '8-open-options-not-implemented', 'binding': '8. Open options (not implemented)', 'line': 215}], 'changed_targets': [], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [], 'hunks': [{'start': 745, 'end': 891, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 1229, 'end': 1229, 'before': '<a id="0-ключові-принципи-чому-саме-так"></a>\n', 'after': ''}, {'start': 1978, 'end': 1978, 'before': '<a id="1-розкладка-на-диску"></a>\n', 'after': ''}, {'start': 2630, 'end': 2630, 'before': '<a id="2-створення-структури--symlink-глобальної-зони"></a>\n', 'after': ''}, {'start': 3026, 'end': 3026, 'before': '<a id="нюанс-з-obsidian"></a>\n', 'after': ''}, {'start': 3582, 'end': 3582, 'before': '<a id="бекап-без-хмари"></a>\n', 'after': ''}, {'start': 3789, 'end': 3789, 'before': '<a id="3-obsidian-mcp--по-порту-на-кожен-project-vault"></a>\n', 'after': ''}, {'start': 4849, 'end': 4849, 'before': '<a id="4-привязка-до-claude-code-scope-на-репо"></a>\n', 'after': ''}, {'start': 5704, 'end': 5704, 'before': '<a id="5-code-review-graph--окремий-граф-на-репо"></a>\n', 'after': ''}, {'start': 6963, 'end': 6963, 'before': '<a id="6-підсумкова-карта"></a>\n', 'after': ''}, {'start': 7726, 'end': 7726, 'before': '<a id="7-чек-ліст-запуску-нового-проєкту"></a>\n', 'after': ''}, {'start': 8318, 'end': 8318, 'before': '<a id="8-відкриті-опції-не-реалізовано"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="0-ключові-принципи-чому-саме-так"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 1, 'record': {'text': '<a id="1-розкладка-на-диску"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 2, 'record': {'text': '<a id="2-створення-структури--symlink-глобальної-зони"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 3, 'record': {'text': '<a id="нюанс-з-obsidian"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 4, 'record': {'text': '<a id="бекап-без-хмари"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 5, 'record': {'text': '<a id="3-obsidian-mcp--по-порту-на-кожен-project-vault"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 6, 'record': {'text': '<a id="4-привязка-до-claude-code-scope-на-репо"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 7, 'record': {'text': '<a id="5-code-review-graph--окремий-граф-на-репо"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 8, 'record': {'text': '<a id="6-підсумкова-карта"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 9, 'record': {'text': '<a id="7-чек-ліст-запуску-нового-проєкту"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 10, 'record': {'text': '<a id="8-відкриті-опції-не-реалізовано"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}], 'pre_literals_sha256': '61520d2e1eceaef13f08453af63b519ff8df420735aa48c3459cf92778a5f821', 'current_literals_sha256': '3a628e9d83fff550854e05585e1d3945c292ed3a9a07b44f2643e2febdac35d5'},
    'docs/translations/en/docs/guides/skills-cheatsheet.md': {'path': 'docs/translations/en/docs/guides/skills-cheatsheet.md', 'pre_anchor_sha256': 'aea18e7bb4588957333a51613b4cb448a46c30b925f0dc1a4e900cb420d4d299', 'current_sha256': 'fb31a60e6c76e8c62e7a42674cee77b23aeaf352506fcb0e90ef1cd1bbce71d8', 'removed_ids': [{'old_id': '-шпаргалка-по-скілах-agentsskills', 'new_id': '-skills-cheatsheet-agentsskills', 'binding': '🧠 Skills cheatsheet (`~/.agents/skills`)', 'line': 3}, {'old_id': 'як-викликаються-скіли', 'new_id': 'how-to-invoke-skills', 'binding': 'How to invoke skills', 'line': 8}, {'old_id': 'ui-рекомендована-точка-входу', 'new_id': 'ui-recommended-entry-point', 'binding': 'UI: recommended entry point', 'line': 14}, {'old_id': '-зміст', 'new_id': '-contents', 'binding': '📑 Contents', 'line': 22}, {'old_id': '1-планування-й-узгодження-grilling--роутинг', 'new_id': '1-planning-and-alignment-grilling--routing', 'binding': '1. Planning and alignment (grilling / routing)', 'line': 50}, {'old_id': 'grilling--авто', 'new_id': 'grilling--auto', 'binding': '`grilling` · `auto`', 'line': 80}, {'old_id': '2-вимоги--задачі--реалізація', 'new_id': '2-requirements--tasks--implementation', 'binding': '2. Requirements → tasks → implementation', 'line': 99}, {'old_id': '3-архітектура-дизайн-і-якість-коду', 'new_id': '3-architecture-design-and-code-quality', 'binding': '3. Architecture, design, and code quality', 'line': 151}, {'old_id': 'codebase-design--авто', 'new_id': 'codebase-design--auto', 'binding': '`codebase-design` · `auto`', 'line': 154}, {'old_id': 'domain-modeling--авто', 'new_id': 'domain-modeling--auto', 'binding': '`domain-modeling` · `auto`', 'line': 164}, {'old_id': 'tdd--авто', 'new_id': 'tdd--auto', 'binding': '`tdd` · `auto`', 'line': 181}, {'old_id': 'diagnosing-bugs--авто', 'new_id': 'diagnosing-bugs--auto', 'binding': '`diagnosing-bugs` · `auto`', 'line': 191}, {'old_id': 'code-review--авто--колізія-назви--див-примітку-нижче', 'new_id': 'code-review--auto--name-collision--see-note-below', 'binding': '`code-review` · `auto` ⚠️ *(name collision — see note below)*', 'line': 201}, {'old_id': 'receiving-code-review--авто--не-pocock--з-obrasuperpowers', 'new_id': 'receiving-code-review--auto--not-pocock--from-obrasuperpowers', 'binding': '`receiving-code-review` · `auto` ⚠️ *(not Pocock — from `obra/superpowers`)*', 'line': 211}, {'old_id': '4-git-merge-і-запобіжники', 'new_id': '4-git-merging-and-safeguards', 'binding': '4. Git, merging, and safeguards', 'line': 223}, {'old_id': 'resolving-merge-conflicts--авто--апстрім-прибрав-2026-09-24-тут-лишили-як-кастомний', 'new_id': 'resolving-merge-conflicts--auto--removed-upstream-on-2026-09-24-retained-here-as-custom', 'binding': '`resolving-merge-conflicts` · `auto` ⚠️ *(removed upstream on 2026-09-24; retained here as custom)*', 'line': 226}, {'old_id': 'git-guardrails-claude-code--авто', 'new_id': 'git-guardrails-claude-code--auto', 'binding': '`git-guardrails-claude-code` · `auto`', 'line': 235}, {'old_id': 'setup-pre-commit--авто', 'new_id': 'setup-pre-commit--auto', 'binding': '`setup-pre-commit` · `auto`', 'line': 244}, {'old_id': 'pr--авто', 'new_id': 'pr--auto', 'binding': '`pr` · `auto`', 'line': 255}, {'old_id': '5-crg--навігація-по-графу-коду-від-code-review-graph-mcp', 'new_id': '5-crg--code-graph-navigation-from-code-review-graph-mcp', 'binding': '5. CRG — code graph navigation *(from code-review-graph MCP)*', 'line': 263}, {'old_id': 'crg-explore-codebase--авто', 'new_id': 'crg-explore-codebase--auto', 'binding': '`crg-explore-codebase` · `auto`', 'line': 266}, {'old_id': 'crg-debug-issue--авто', 'new_id': 'crg-debug-issue--auto', 'binding': '`crg-debug-issue` · `auto`', 'line': 273}, {'old_id': 'crg-refactor-safely--авто', 'new_id': 'crg-refactor-safely--auto', 'binding': '`crg-refactor-safely` · `auto`', 'line': 280}, {'old_id': 'crg-review-changes--авто', 'new_id': 'crg-review-changes--auto', 'binding': '`crg-review-changes` · `auto`', 'line': 287}, {'old_id': '6-прототипування-навчання-передача-контексту', 'new_id': '6-prototyping-learning-and-context-handoff', 'binding': '6. Prototyping, learning, and context handoff', 'line': 296}, {'old_id': 'frontend-design--авто--не-pocock--форк-anthropicsskills', 'new_id': 'frontend-design--auto--not-pocock--a-fork-of-anthropicsskills', 'binding': '`frontend-design` · `auto` ⚠️ *(not Pocock — a fork of `anthropics/skills`)*', 'line': 307}, {'old_id': 'research--авто--не-плутай-з-deep-research-див-примітку-нижче', 'new_id': 'research--auto--do-not-confuse-with-deep-research-see-note-below', 'binding': '`research` · `auto` ⚠️ *(do not confuse with `deep-research`; see note below)*', 'line': 324}, {'old_id': '7-утиліти-міграції-метаскіли', 'new_id': '7-utilities-migrations-and-meta-skills', 'binding': '7. Utilities, migrations, and meta-skills', 'line': 360}, {'old_id': 'migrate-to-shoehorn--авто', 'new_id': 'migrate-to-shoehorn--auto', 'binding': '`migrate-to-shoehorn` · `auto`', 'line': 363}, {'old_id': 'scaffold-exercises--авто', 'new_id': 'scaffold-exercises--auto', 'binding': '`scaffold-exercises` · `auto`', 'line': 372}, {'old_id': 'writing-for-agents--авто', 'new_id': 'writing-for-agents--auto', 'binding': '`writing-for-agents` · `auto`', 'line': 381}, {'old_id': 'wizard--авто', 'new_id': 'wizard--auto', 'binding': '`wizard` · `auto`', 'line': 391}, {'old_id': 'caveman--авто', 'new_id': 'caveman--auto', 'binding': '`caveman` · `auto`', 'line': 414}, {'old_id': '-конвеєр-ai-factory-власні-скіли-не-pocock', 'new_id': '-ai-factory-pipeline-custom-skills-not-pocock', 'binding': '🏭 AI-factory pipeline *(custom skills, not Pocock)*', 'line': 425}, {'old_id': 'repo-bootstrap--авто', 'new_id': 'repo-bootstrap--auto', 'binding': '`repo-bootstrap` · `auto`', 'line': 445}, {'old_id': 'cto-research--авто', 'new_id': 'cto-research--auto', 'binding': '`cto-research` · `auto`', 'line': 456}, {'old_id': 'cto-agenda--авто', 'new_id': 'cto-agenda--auto', 'binding': '`cto-agenda` · `auto`', 'line': 466}, {'old_id': 'spec-flow--авто', 'new_id': 'spec-flow--auto', 'binding': '`spec-flow` · `auto`', 'line': 476}, {'old_id': 'plan-critique--авто', 'new_id': 'plan-critique--auto', 'binding': '`plan-critique` · `auto`', 'line': 486}, {'old_id': 'plan-defense--авто', 'new_id': 'plan-defense--auto', 'binding': '`plan-defense` · `auto`', 'line': 497}, {'old_id': 'acceptance-spec--авто', 'new_id': 'acceptance-spec--auto', 'binding': '`acceptance-spec` · `auto`', 'line': 507}, {'old_id': 'ship-report--авто', 'new_id': 'ship-report--auto', 'binding': '`ship-report` · `auto`', 'line': 518}, {'old_id': 'post-deploy-check--авто', 'new_id': 'post-deploy-check--auto', 'binding': '`post-deploy-check` · `auto`', 'line': 530}, {'old_id': 'антипатерни-', 'new_id': 'anti-patterns-', 'binding': 'Anti-patterns ❌', 'line': 542}, {'old_id': '-ponytail--режим-лінивого-сеньйора-6-скілів-не-pocock', 'new_id': '-ponytail--lazy-senior-mode-6-skills-not-pocock', 'binding': '🎀 Ponytail — lazy senior mode *(6 skills, not Pocock)*', 'line': 552}, {'old_id': 'ponytail--авто-режим-тримається-до-кінця-сесії', 'new_id': 'ponytail--auto-mode-lasts-until-session-end', 'binding': '`ponytail` · `auto` *(mode, lasts until session end)*', 'line': 578}, {'old_id': 'ponytail-review--авто', 'new_id': 'ponytail-review--auto', 'binding': '`ponytail-review` · `auto`', 'line': 588}, {'old_id': 'ponytail-audit--авто', 'new_id': 'ponytail-audit--auto', 'binding': '`ponytail-audit` · `auto`', 'line': 598}, {'old_id': 'ponytail-debt--авто', 'new_id': 'ponytail-debt--auto', 'binding': '`ponytail-debt` · `auto`', 'line': 608}, {'old_id': 'ponytail-gain--авто-разова-картка', 'new_id': 'ponytail-gain--auto-one-off-card', 'binding': '`ponytail-gain` · `auto` *(one-off card)*', 'line': 618}, {'old_id': 'ponytail-help--авто-разова-картка', 'new_id': 'ponytail-help--auto-one-off-card', 'binding': '`ponytail-help` · `auto` *(one-off card)*', 'line': 628}, {'old_id': 'комбо-з-рештою-сховища', 'new_id': 'combinations-with-the-rest-of-the-store', 'binding': 'Combinations with the rest of the store', 'line': 637}, {'old_id': 'антипатерни--1', 'new_id': 'anti-patterns--1', 'binding': 'Anti-patterns ❌', 'line': 645}, {'old_id': '-звязки-скілів-комбо-для-кращого-результату', 'new_id': '-skill-combinations-for-better-results', 'binding': '🔗 Skill combinations (for better results)', 'line': 655}, {'old_id': 'планування--доставка', 'new_id': 'planning--delivery', 'binding': 'Planning → delivery', 'line': 660}, {'old_id': 'grilling--ядро-інтервю-лупа-смикається-зсередини-інших-скілів', 'new_id': 'grilling--interview-loop-core-called-from-inside-other-skills', 'binding': '`grilling` — interview-loop core *(called from inside other skills)*', 'line': 663}, {'old_id': 'grill-me--to-spec--to-tickets--implement--флагманський-рецепт-доставки-фічі', 'new_id': 'grill-me--to-spec--to-tickets--implement--flagship-feature-delivery-recipe', 'binding': '`grill-me` → `to-spec` → `to-tickets` → `implement` 🏁 *(flagship feature-delivery recipe)*', 'line': 678}, {'old_id': 'wayfinder--to-tickets-по-кожному-investigation-тікету-коли-фіча-завелика-для-одної-сесії', 'new_id': 'wayfinder--to-tickets-per-investigation-ticket-when-a-feature-is-too-large-for-one-session', 'binding': '`wayfinder` → `to-tickets` (per investigation ticket) *(when a feature is too large for one session)*', 'line': 698}, {'old_id': 'research--grill-with-docs--domain-modeling-коли-рішення-залежить-від-незнайомого-apiдоки', 'new_id': 'research--grill-with-docs--domain-modeling-when-a-decision-depends-on-unfamiliar-apidocs', 'binding': '`research` → `grill-with-docs` ↔ `domain-modeling` *(when a decision depends on unfamiliar API/docs)*', 'line': 732}, {'old_id': 'дизайн--архітектура', 'new_id': 'design--architecture', 'binding': 'Design / architecture', 'line': 748}, {'old_id': 'improve-codebase-architecture--codebase-design--grill-me--флагманський-рецепт-рефакторингу', 'new_id': 'improve-codebase-architecture--codebase-design--grill-me--flagship-refactoring-recipe', 'binding': '`improve-codebase-architecture` → `codebase-design` → `grill-me` 🏁 *(flagship refactoring recipe)*', 'line': 751}, {'old_id': 'баги--якість', 'new_id': 'bugs--quality', 'binding': 'Bugs / quality', 'line': 798}, {'old_id': 'tdd--code-review-skill-перед-mergepr--стандарти--spec', 'new_id': 'tdd--code-review-skill-before-mergepr--standards--spec', 'binding': '`tdd` → `code-review` (skill) *(before merge/PR — Standards + Spec)*', 'line': 817}, {'old_id': 'code-review--code-review--crg-review-changes--receiving-code-review-після-ревю--як-реагувати-на-фідбек', 'new_id': 'code-review--code-review--crg-review-changes--receiving-code-review-after-review--responding-to-feedback', 'binding': '`code-review` / `/code-review` / `crg-review-changes` → `receiving-code-review` *(after review — responding to feedback)*', 'line': 829}, {'old_id': 'crg-refactor-safely--tdd--або-resolving-merge-conflicts--tdd', 'new_id': 'crg-refactor-safely--tdd--or-resolving-merge-conflicts--tdd', 'binding': '`crg-refactor-safely` → `tdd`  *(or `resolving-merge-conflicts` → `tdd`)*', 'line': 859}, {'old_id': 'чистка--дублі--зламана-логіка--стилі--motion', 'new_id': 'cleanup--duplicates--broken-logic--styles--motion', 'binding': 'Cleanup 🧹 *(duplicates / broken logic / styles / motion)*', 'line': 888}, {'old_id': 'вхідні--процес', 'new_id': 'intake--process', 'binding': 'Intake / process', 'line': 909}, {'old_id': 'setup-matt-pocock-skills--усі-engineering-скіли', 'new_id': 'setup-matt-pocock-skills--all-engineering-skills', 'binding': '`setup-matt-pocock-skills` → *(all engineering skills)*', 'line': 912}, {'old_id': 'мета-обгортки', 'new_id': 'meta-wrappers', 'binding': 'Meta-wrappers', 'line': 941}, {'old_id': 'міграція--парність-legacy--new', 'new_id': 'migration--parity-legacy--new', 'binding': 'Migration / parity (legacy → new)', 'line': 946}, {'old_id': 'legacy--new-parity--аудит--gap--порт--звірка', 'new_id': 'legacy--new-parity--audit--gap--port--verify', 'binding': 'legacy → new parity 🏁 *(audit → gap → port → verify)*', 'line': 949}, {'old_id': '-скіл--mcp-комбо-для-кращого-результату', 'new_id': '-skill--mcp-combinations-for-better-results', 'binding': '➕ Skill + MCP (combinations for better results)', 'line': 974}, {'old_id': 'кодинг-із-актуальною-докою', 'new_id': 'coding-with-current-documentation', 'binding': 'Coding with current documentation', 'line': 979}, {'old_id': 'візуальний--браузерний-dev-loop', 'new_id': 'visual--browser-development-loop', 'binding': 'Visual / browser development loop', 'line': 997}, {'old_id': 'diagnosing-bugs--playwright--chrome-devtools-mcp_docker--плагін', 'new_id': 'diagnosing-bugs--playwright--chrome-devtools-mcp_docker--plugin', 'binding': '`diagnosing-bugs` + `playwright` / `chrome-devtools` *(MCP_DOCKER / plugin)*', 'line': 1008}, {'old_id': 'дизайн--код', 'new_id': 'design--code', 'binding': 'Design → code', 'line': 1024}, {'old_id': 'prototype--дизайн-задачі--figma-desktop-mcp', 'new_id': 'prototype--design-tasks--figma-desktop-mcp', 'binding': '`prototype` / design tasks + `Figma Desktop` *(MCP)*', 'line': 1027}, {'old_id': 'навігація--архітектура-великого-кодбейзу', 'new_id': 'navigation--architecture-of-a-large-codebase', 'binding': 'Navigation / architecture of a large codebase', 'line': 1043}, {'old_id': '-mcp-сервери-на-машині', 'new_id': '-mcp-servers-on-the-machine', 'binding': '🔌 MCP servers on the machine', 'line': 1065}, {'old_id': 'спільні-mcp-є-і-в-claude-і-в-cursor', 'new_id': 'shared-mcps-both-claude-and-cursor', 'binding': 'Shared MCPs (both Claude and Cursor)', 'line': 1071}, {'old_id': 'figma-desktop-локальний-1270013845mcp', 'new_id': 'figma-desktop-local-1270013845mcp', 'binding': '`Figma Desktop` *(local, `127.0.0.1:3845/mcp`)*', 'line': 1083}, {'old_id': 'code-review-graph-локальний-бінар-привязаний-до-cassiopeia-admin-ui', 'new_id': 'code-review-graph-local-binary-bound-to-cassiopeia-admin-ui', 'binding': '`code-review-graph` *(local binary, bound to `cassiopeia-admin-ui`)*', 'line': 1092}, {'old_id': 'тільки-claude', 'new_id': 'claude-only', 'binding': 'Claude only', 'line': 1101}, {'old_id': 'figma-плагін-figma-remote-mcpfigmacommcp', 'new_id': 'figma-plugin-figma-remote-mcpfigmacommcp', 'binding': '`figma` *(plugin `figma`, remote `mcp.figma.com/mcp`)*', 'line': 1104}, {'old_id': 'chrome-devtools-плагін-figma-friend-також-проєкт-cargodes', 'new_id': 'chrome-devtools-plugin-figma-friend-also-project-cargodes', 'binding': '`chrome-devtools` *(plugin `figma-friend`; also project `cargo/des`)*', 'line': 1113}, {'old_id': 'тільки-cursor', 'new_id': 'cursor-only', 'binding': 'Cursor only', 'line': 1122}, {'old_id': '-плагінні--вбудовані-скіли-поза-agentsskills', 'new_id': '-plugin--built-in-skills-outside-agentsskills', 'binding': '🧩 Plugin / built-in skills (outside `~/.agents/skills`)', 'line': 1129}, {'old_id': 'плагінні-скіли-з-claudeplugins-керуються-маркетплейсом', 'new_id': 'plugin-skills-from-claudeplugins-managed-by-the-marketplace', 'binding': 'Plugin skills *(from `~/.claude/plugins`, managed by the marketplace)*', 'line': 1134}, {'old_id': 'плагін-figma-friend-v001-marketplace-figma-friend', 'new_id': 'figma-friend-plugin-v001-marketplace-figma-friend', 'binding': '`figma-friend` plugin *(v0.0.1, marketplace `figma-friend`)*', 'line': 1137}, {'old_id': 'плагін-figma-офіційний-v2260', 'new_id': 'figma-plugin-official-v2260', 'binding': '`figma` plugin *(official, v2.2.60)*', 'line': 1146}, {'old_id': 'вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску', 'new_id': 'built-in-harness-skills-ship-with-claude-code-not-on-disk', 'binding': 'Built-in harness skills *(ship with Claude Code; not on disk)*', 'line': 1163}, {'old_id': '-наскрізні-сценарії-end-to-end-промти', 'new_id': '-end-to-end-scenarios-prompts', 'binding': '🎬 End-to-end scenarios (prompts)', 'line': 1189}, {'old_id': '1-нова-фіча-від-нуля-до-pr', 'new_id': '1-new-feature-from-zero-to-pr', 'binding': '1. New feature from zero to PR', 'line': 1194}, {'old_id': '2-архітектурний-рефактор-флагман-', 'new_id': '2-architectural-refactor-flagship-', 'binding': '2. Architectural refactor (flagship 🏁)', 'line': 1199}, {'old_id': '3-складний-рантайм-баг', 'new_id': '3-difficult-runtime-bug', 'binding': '3. Difficult runtime bug', 'line': 1204}, {'old_id': '4-ui-з-макета-до-робочого-екрана', 'new_id': '4-ui-from-mockup-to-working-screen', 'binding': '4. UI from mockup to working screen', 'line': 1209}, {'old_id': '5-розгрібання-вхідного-потоку', 'new_id': '5-processing-incoming-work', 'binding': '5. Processing incoming work', 'line': 1214}, {'old_id': '6-дослідження-незнайомої-технології--рішення-в-adr', 'new_id': '6-researching-unfamiliar-technology--decision-in-an-adr', 'binding': '6. Researching unfamiliar technology → decision in an ADR', 'line': 1219}, {'old_id': '7-перенесення-legacy-функціоналу-на-нові-компоненти', 'new_id': '7-moving-legacy-functionality-to-new-components', 'binding': '7. Moving legacy functionality to new components', 'line': 1224}, {'old_id': '8-чистка-дублі--зламана-логіка--стилі--анімації', 'new_id': '8-cleanup-duplicates--broken-logic--styles--animations', 'binding': '8. Cleanup: duplicates / broken logic / styles / animations', 'line': 1229}, {'old_id': '9-merge-коректне-вирішення-конфліктів--фікс-зламаного-алгоритму', 'new_id': '9-merge-correct-conflict-resolution--fixing-a-broken-algorithm', 'binding': '9. Merge: correct conflict resolution + fixing a broken algorithm', 'line': 1234}, {'old_id': '10-pull-коректне-вирішення-конфліктів--фікс-зламаного-алгоритму', 'new_id': '10-pull-correct-conflict-resolution--fixing-a-broken-algorithm', 'binding': '10. Pull: correct conflict resolution + fixing a broken algorithm', 'line': 1239}, {'old_id': '11-реліз-готовність-security-review-перед-релізом', 'new_id': '11-release-readiness-security-review-before-release', 'binding': '11. Release readiness: security-review before release', 'line': 1244}, {'old_id': '12-завершення-сесії', 'new_id': '12-ending-a-session', 'binding': '12. Ending a session', 'line': 1249}, {'old_id': '-ревю-пас-що-перевіряє-себе-як-отримувати-щоразу', 'new_id': '-a-self-checking-review-pass-how-to-get-one-every-time', 'binding': '🔬 A self-checking review pass (how to get one every time)', 'line': 1256}, {'old_id': 'словник-без-нього-розділ-не-читається', 'new_id': 'vocabulary-needed-to-read-this-section', 'binding': 'Vocabulary (needed to read this section)', 'line': 1262}, {'old_id': '6-інваріантів', 'new_id': '6-invariants', 'binding': '6 invariants', 'line': 1281}, {'old_id': 'кошики-findings', 'new_id': 'finding-buckets', 'binding': 'Finding buckets', 'line': 1291}, {'old_id': 'промт-копіпаст', 'new_id': 'prompt-copypaste', 'binding': 'Prompt (copy/paste)', 'line': 1296}, {'old_id': 'definition-of-done-для-workerа-щоб-пас-був-дешевим', 'new_id': 'worker-definition-of-done-to-make-the-pass-cheap', 'binding': 'Worker definition of done (to make the pass cheap)', 'line': 1315}, {'old_id': 'базлайни--у-файл-не-в-голову', 'new_id': 'baselines--in-a-file-not-in-your-head', 'binding': 'Baselines — in a file, not in your head', 'line': 1324}, {'old_id': 'ціна-і-що-різати', 'new_id': 'cost-and-what-to-cut', 'binding': 'Cost and what to cut', 'line': 1329}, {'old_id': 'звязки', 'new_id': 'connections', 'binding': 'Connections', 'line': 1334}, {'old_id': '-як-скіл-влаштований-під-капотом', 'new_id': '-how-a-skill-works-under-the-hood', 'binding': '🛠️ How a skill works (under the hood)', 'line': 1344}, {'old_id': '-обслуговування', 'new_id': '-maintenance', 'binding': '⚙️ Maintenance', 'line': 1370}, {'old_id': 'збереження-локальних-виправлень-2026-10-14', 'new_id': 'preserving-local-fixes-2026-10-14', 'binding': 'Preserving local fixes (2026-10-14)', 'line': 1385}], 'changed_targets': [{'old_target': '#як-викликаються-скіли', 'new_target': '#how-to-invoke-skills', 'count': 1, 'line': 25}, {'old_target': '#1-планування-й-узгодження-grilling--роутинг', 'new_target': '#1-planning-and-alignment-grilling--routing', 'count': 1, 'line': 27}, {'old_target': '#2-вимоги--задачі--реалізація', 'new_target': '#2-requirements--tasks--implementation', 'count': 1, 'line': 28}, {'old_target': '#3-архітектура-дизайн-і-якість-коду', 'new_target': '#3-architecture-design-and-code-quality', 'count': 1, 'line': 29}, {'old_target': '#4-git-merge-і-запобіжники', 'new_target': '#4-git-merging-and-safeguards', 'count': 1, 'line': 30}, {'old_target': '#5-crg--навігація-по-графу-коду-від-code-review-graph-mcp', 'new_target': '#5-crg--code-graph-navigation-from-code-review-graph-mcp', 'count': 1, 'line': 31}, {'old_target': '#6-прототипування-навчання-передача-контексту', 'new_target': '#6-prototyping-learning-and-context-handoff', 'count': 1, 'line': 32}, {'old_target': '#7-утиліти-міграції-метаскіли', 'new_target': '#7-utilities-migrations-and-meta-skills', 'count': 1, 'line': 33}, {'old_target': '#-конвеєр-ai-factory-власні-скіли-не-pocock', 'new_target': '#-ai-factory-pipeline-custom-skills-not-pocock', 'count': 1, 'line': 34}, {'old_target': '#-ponytail--режим-лінивого-сеньйора-6-скілів-не-pocock', 'new_target': '#-ponytail--lazy-senior-mode-6-skills-not-pocock', 'count': 1, 'line': 35}, {'old_target': '#-звязки-скілів-комбо-для-кращого-результату', 'new_target': '#-skill-combinations-for-better-results', 'count': 1, 'line': 36}, {'old_target': '#планування--доставка', 'new_target': '#planning--delivery', 'count': 1, 'line': 37}, {'old_target': '#дизайн--архітектура', 'new_target': '#design--architecture', 'count': 1, 'line': 37}, {'old_target': '#баги--якість', 'new_target': '#bugs--quality', 'count': 1, 'line': 37}, {'old_target': '#вхідні--процес', 'new_target': '#intake--process', 'count': 1, 'line': 37}, {'old_target': '#міграція--парність-legacy--new', 'new_target': '#migration--parity-legacy--new', 'count': 1, 'line': 37}, {'old_target': '#-скіл--mcp-комбо-для-кращого-результату', 'new_target': '#-skill--mcp-combinations-for-better-results', 'count': 1, 'line': 38}, {'old_target': '#-mcp-сервери-на-машині', 'new_target': '#-mcp-servers-on-the-machine', 'count': 1, 'line': 39}, {'old_target': '#спільні-mcp-є-і-в-claude-і-в-cursor', 'new_target': '#shared-mcps-both-claude-and-cursor', 'count': 1, 'line': 40}, {'old_target': '#тільки-claude', 'new_target': '#claude-only', 'count': 1, 'line': 40}, {'old_target': '#тільки-cursor', 'new_target': '#cursor-only', 'count': 1, 'line': 40}, {'old_target': '#-плагінні--вбудовані-скіли-поза-agentsskills', 'new_target': '#-plugin--built-in-skills-outside-agentsskills', 'count': 1, 'line': 41}, {'old_target': '#плагінні-скіли-з-claudeplugins-керуються-маркетплейсом', 'new_target': '#plugin-skills-from-claudeplugins-managed-by-the-marketplace', 'count': 1, 'line': 42}, {'old_target': '#вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску', 'new_target': '#built-in-harness-skills-ship-with-claude-code-not-on-disk', 'count': 1, 'line': 42}, {'old_target': '#-наскрізні-сценарії-end-to-end-промти', 'new_target': '#-end-to-end-scenarios-prompts', 'count': 1, 'line': 43}, {'old_target': '#-ревю-пас-що-перевіряє-себе-як-отримувати-щоразу', 'new_target': '#-a-self-checking-review-pass-how-to-get-one-every-time', 'count': 1, 'line': 44}, {'old_target': '#-як-скіл-влаштований-під-капотом', 'new_target': '#-how-a-skill-works-under-the-hood', 'count': 1, 'line': 45}, {'old_target': '#-обслуговування', 'new_target': '#-maintenance', 'count': 1, 'line': 46}, {'old_target': '#вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску', 'new_target': '#built-in-harness-skills-ship-with-claude-code-not-on-disk', 'count': 1, 'line': 206}, {'old_target': '#-обслуговування', 'new_target': '#-maintenance', 'count': 1, 'line': 216}, {'old_target': '#вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску', 'new_target': '#built-in-harness-skills-ship-with-claude-code-not-on-disk', 'count': 1, 'line': 329}, {'old_target': '#-скіл--mcp-комбо-для-кращого-результату', 'new_target': '#-skill--mcp-combinations-for-better-results', 'count': 1, 'line': 658}, {'old_target': '#чистка--дублі--зламана-логіка--стилі--motion', 'new_target': '#cleanup--duplicates--broken-logic--styles--motion', 'count': 1, 'line': 969}, {'old_target': '#-плагінні--вбудовані-скіли-поза-agentsskills', 'new_target': '#-plugin--built-in-skills-outside-agentsskills', 'count': 1, 'line': 1106}, {'old_target': '#чистка--дублі--зламана-логіка--стилі--motion', 'new_target': '#cleanup--duplicates--broken-logic--styles--motion', 'count': 1, 'line': 1237}, {'old_target': '#чистка--дублі--зламана-логіка--стилі--motion', 'new_target': '#cleanup--duplicates--broken-logic--styles--motion', 'count': 1, 'line': 1242}], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [{'before': '### `ask-matt` · `/команда`\n', 'after': '### `ask-matt` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'ask-matt--команда', 'new_native_id': 'ask-matt--command', 'preserved_body_literal': '/команда'}, {'before': '### `grill-me` · `/команда`\n', 'after': '### `grill-me` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'grill-me--команда', 'new_native_id': 'grill-me--command', 'preserved_body_literal': '/команда'}, {'before': '### `grill-with-docs` · `/команда`\n', 'after': '### `grill-with-docs` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'grill-with-docs--команда', 'new_native_id': 'grill-with-docs--command', 'preserved_body_literal': '/команда'}, {'before': '### `to-questionnaire` · `/команда`\n', 'after': '### `to-questionnaire` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'to-questionnaire--команда', 'new_native_id': 'to-questionnaire--command', 'preserved_body_literal': '/команда'}, {'before': '### `to-spec` · `/команда`\n', 'after': '### `to-spec` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'to-spec--команда', 'new_native_id': 'to-spec--command', 'preserved_body_literal': '/команда'}, {'before': '### `to-tickets` · `/команда`\n', 'after': '### `to-tickets` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'to-tickets--команда', 'new_native_id': 'to-tickets--command', 'preserved_body_literal': '/команда'}, {'before': '### `triage` · `/команда`\n', 'after': '### `triage` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'triage--команда', 'new_native_id': 'triage--command', 'preserved_body_literal': '/команда'}, {'before': '### `implement` · `/команда`\n', 'after': '### `implement` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'implement--команда', 'new_native_id': 'implement--command', 'preserved_body_literal': '/команда'}, {'before': '### `wayfinder` · `/команда`\n', 'after': '### `wayfinder` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'wayfinder--команда', 'new_native_id': 'wayfinder--command', 'preserved_body_literal': '/команда'}, {'before': '### `implement-spec` · `/команда`\n', 'after': '### `implement-spec` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'implement-spec--команда', 'new_native_id': 'implement-spec--command', 'preserved_body_literal': '/команда'}, {'before': '### `improve-codebase-architecture` · `/команда`\n', 'after': '### `improve-codebase-architecture` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'improve-codebase-architecture--команда', 'new_native_id': 'improve-codebase-architecture--command', 'preserved_body_literal': '/команда'}, {'before': '### `prototype` · `/команда`\n', 'after': '### `prototype` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'prototype--команда', 'new_native_id': 'prototype--command', 'preserved_body_literal': '/команда'}, {'before': '### `teach` · `/команда`\n', 'after': '### `teach` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'teach--команда', 'new_native_id': 'teach--command', 'preserved_body_literal': '/команда'}, {'before': '### `handoff` · `/команда`\n', 'after': '### `handoff` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'handoff--команда', 'new_native_id': 'handoff--command', 'preserved_body_literal': '/команда'}, {'before': '### `retro` · `/команда`\n', 'after': '### `retro` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'retro--команда', 'new_native_id': 'retro--command', 'preserved_body_literal': '/команда'}, {'before': '### `wait-what` · `/команда`\n', 'after': '### `wait-what` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'wait-what--команда', 'new_native_id': 'wait-what--command', 'preserved_body_literal': '/команда'}, {'before': '### `setup-matt-pocock-skills` · `/команда`\n', 'after': '### `setup-matt-pocock-skills` · command\n\nOriginal command-category placeholder: `/команда`.\n\n', 'old_native_id': 'setup-matt-pocock-skills--команда', 'new_native_id': 'setup-matt-pocock-skills--command', 'preserved_body_literal': '/команда'}], 'hunks': [{'start': 476, 'end': 622, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 627, 'end': 627, 'before': '<a id="-шпаргалка-по-скілах-agentsskills"></a>\n', 'after': ''}, {'start': 876, 'end': 876, 'before': '<a id="як-викликаються-скіли"></a>\n', 'after': ''}, {'start': 1398, 'end': 1398, 'before': '<a id="ui-рекомендована-точка-входу"></a>\n', 'after': ''}, {'start': 2245, 'end': 2245, 'before': '<a id="-зміст"></a>\n', 'after': ''}, {'start': 2286, 'end': 2306, 'before': 'як-викликаються-скіли', 'after': 'how-to-invoke-skills'}, {'start': 2381, 'end': 5241, 'before': 'планування-й-узгодження-grilling--роутинг) — `ask-matt` · `grill-me` · `grill-with-docs` · `grilling` · `to-questionnaire` · **`cto-research`** · **`cto-agenda`** · **`plan-critique`** · **`plan-defense`** · **`acceptance-spec`**\n  2. [Requirements → tasks → implementation](#2-вимоги--задачі--реалізація) — `to-spec` · `to-tickets` · `triage` · `implement` · `implement-spec` · `wayfinder` · **`spec-flow`**\n  3. [Architecture, design, and code quality](#3-архітектура-дизайн-і-якість-коду) — `codebase-design` · `domain-modeling` · `improve-codebase-architecture` · `tdd` · `diagnosing-bugs` · `code-review` · `receiving-code-review`\n  4. [Git, merging, and safeguards](#4-git-merge-і-запобіжники) — `resolving-merge-conflicts` · `git-guardrails-claude-code` · `setup-pre-commit` · `pr`\n  5. [CRG — code graph navigation](#5-crg--навігація-по-графу-коду-від-code-review-graph-mcp) — `crg-explore-codebase` · `crg-debug-issue` · `crg-refactor-safely` · `crg-review-changes`\n  6. [Prototyping, learning, handoff](#6-прототипування-навчання-передача-контексту) — `prototype` · `frontend-design` · `research` · `teach` · `handoff` · `retro` · **`ship-report`** · **`post-deploy-check`**\n  7. [Utilities, migrations, meta-skills](#7-утиліти-міграції-метаскіли) — `migrate-to-shoehorn` · `scaffold-exercises` · `writing-for-agents` · `wizard` · `wait-what` · `setup-matt-pocock-skills` · `caveman` · **`repo-bootstrap`**\n- [🏭 AI-factory pipeline (9 custom skills)](#-конвеєр-ai-factory-власні-скіли-не-pocock)\n- [🎀 Ponytail — lazy senior mode (6 skills)](#-ponytail--режим-лінивого-сеньйора-6-скілів-не-pocock) — **`ponytail`** · **`ponytail-review`** · **`ponytail-audit`** · **`ponytail-debt`** · **`ponytail-gain`** · **`ponytail-help`**\n- [🔗 Skill combinations](#-звязки-скілів-комбо-для-кращого-результату)\n  - [Planning → delivery](#планування--доставка) · [Design / architecture](#дизайн--архітектура) · [Bugs / quality](#баги--якість) · [Intake / process](#вхідні--процес) · [Migration / parity](#міграція--парність-legacy--new)\n  - [➕ Skill + MCP](#-скіл--mcp-комбо-для-кращого-результату)\n- [🔌 MCP servers on the machine](#-mcp-сервери-на-машині)\n  - [Shared MCPs](#спільні-mcp-є-і-в-claude-і-в-cursor) · [Claude only](#тільки-claude) · [Cursor only](#тільки-cursor)\n- [🧩 Plugin / built-in skills](#-плагінні--вбудовані-скіли-поза-agentsskills)\n  - [Plugin skills (figma, figma-friend)](#плагінні-скіли-з-claudeplugins-керуються-маркетплейсом) · [Built-in harness skills](#вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску)\n- [🎬 End-to-end scenarios (prompts)](#-наскрізні-сценарії-end-to-end-промти)\n- [🔬 A self-checking review pass (how to get one every time)](#-ревю-пас-що-перевіряє-себе-як-отримувати-щоразу)\n- [🛠️ How a skill works (under the hood)](#-як-скіл-влаштований-під-капотом)\n- [⚙️ Maintenance](#-обслуговування', 'after': 'planning-and-alignment-grilling--routing) — `ask-matt` · `grill-me` · `grill-with-docs` · `grilling` · `to-questionnaire` · **`cto-research`** · **`cto-agenda`** · **`plan-critique`** · **`plan-defense`** · **`acceptance-spec`**\n  2. [Requirements → tasks → implementation](#2-requirements--tasks--implementation) — `to-spec` · `to-tickets` · `triage` · `implement` · `implement-spec` · `wayfinder` · **`spec-flow`**\n  3. [Architecture, design, and code quality](#3-architecture-design-and-code-quality) — `codebase-design` · `domain-modeling` · `improve-codebase-architecture` · `tdd` · `diagnosing-bugs` · `code-review` · `receiving-code-review`\n  4. [Git, merging, and safeguards](#4-git-merging-and-safeguards) — `resolving-merge-conflicts` · `git-guardrails-claude-code` · `setup-pre-commit` · `pr`\n  5. [CRG — code graph navigation](#5-crg--code-graph-navigation-from-code-review-graph-mcp) — `crg-explore-codebase` · `crg-debug-issue` · `crg-refactor-safely` · `crg-review-changes`\n  6. [Prototyping, learning, handoff](#6-prototyping-learning-and-context-handoff) — `prototype` · `frontend-design` · `research` · `teach` · `handoff` · `retro` · **`ship-report`** · **`post-deploy-check`**\n  7. [Utilities, migrations, meta-skills](#7-utilities-migrations-and-meta-skills) — `migrate-to-shoehorn` · `scaffold-exercises` · `writing-for-agents` · `wizard` · `wait-what` · `setup-matt-pocock-skills` · `caveman` · **`repo-bootstrap`**\n- [🏭 AI-factory pipeline (9 custom skills)](#-ai-factory-pipeline-custom-skills-not-pocock)\n- [🎀 Ponytail — lazy senior mode (6 skills)](#-ponytail--lazy-senior-mode-6-skills-not-pocock) — **`ponytail`** · **`ponytail-review`** · **`ponytail-audit`** · **`ponytail-debt`** · **`ponytail-gain`** · **`ponytail-help`**\n- [🔗 Skill combinations](#-skill-combinations-for-better-results)\n  - [Planning → delivery](#planning--delivery) · [Design / architecture](#design--architecture) · [Bugs / quality](#bugs--quality) · [Intake / process](#intake--process) · [Migration / parity](#migration--parity-legacy--new)\n  - [➕ Skill + MCP](#-skill--mcp-combinations-for-better-results)\n- [🔌 MCP servers on the machine](#-mcp-servers-on-the-machine)\n  - [Shared MCPs](#shared-mcps-both-claude-and-cursor) · [Claude only](#claude-only) · [Cursor only](#cursor-only)\n- [🧩 Plugin / built-in skills](#-plugin--built-in-skills-outside-agentsskills)\n  - [Plugin skills (figma, figma-friend)](#plugin-skills-from-claudeplugins-managed-by-the-marketplace) · [Built-in harness skills](#built-in-harness-skills-ship-with-claude-code-not-on-disk)\n- [🎬 End-to-end scenarios (prompts)](#-end-to-end-scenarios-prompts)\n- [🔬 A self-checking review pass (how to get one every time)](#-a-self-checking-review-pass-how-to-get-one-every-time)\n- [🛠️ How a skill works (under the hood)](#-how-a-skill-works-under-the-hood)\n- [⚙️ Maintenance](#-maintenance'}, {'start': 5249, 'end': 5249, 'before': '<a id="1-планування-й-узгодження-grilling--роутинг"></a>\n', 'after': ''}, {'start': 5317, 'end': 5377, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 5931, 'end': 5991, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 6529, 'end': 6589, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 7133, 'end': 7133, 'before': '<a id="grilling--авто"></a>\n', 'after': ''}, {'start': 7599, 'end': 7659, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 8285, 'end': 8285, 'before': '<a id="2-вимоги--задачі--реалізація"></a>\n', 'after': ''}, {'start': 8346, 'end': 8406, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 8876, 'end': 8936, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 9329, 'end': 9389, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 9768, 'end': 9828, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 10223, 'end': 10283, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 10942, 'end': 11002, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 11612, 'end': 11612, 'before': '<a id="3-архітектура-дизайн-і-якість-коду"></a>\n', 'after': ''}, {'start': 11658, 'end': 11658, 'before': '<a id="codebase-design--авто"></a>\n', 'after': ''}, {'start': 12196, 'end': 12196, 'before': '<a id="domain-modeling--авто"></a>\n', 'after': ''}, {'start': 12688, 'end': 12748, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 13189, 'end': 13189, 'before': '<a id="tdd--авто"></a>\n', 'after': ''}, {'start': 13661, 'end': 13661, 'before': '<a id="diagnosing-bugs--авто"></a>\n', 'after': ''}, {'start': 14162, 'end': 14162, 'before': '<a id="code-review--авто--колізія-назви--див-примітку-нижче"></a>\n', 'after': ''}, {'start': 14798, 'end': 14855, 'before': 'вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску', 'after': 'built-in-harness-skills-ship-with-claude-code-not-on-disk'}, {'start': 15324, 'end': 15324, 'before': '<a id="receiving-code-review--авто--не-pocock--з-obrasuperpowers"></a>\n', 'after': ''}, {'start': 16244, 'end': 16255, 'before': 'обслуговування', 'after': 'maintenance'}, {'start': 16719, 'end': 16719, 'before': '<a id="4-git-merge-і-запобіжники"></a>\n', 'after': ''}, {'start': 16755, 'end': 16755, 'before': '<a id="resolving-merge-conflicts--авто--апстрім-прибрав-2026-09-24-тут-лишили-як-кастомний"></a>\n', 'after': ''}, {'start': 17201, 'end': 17201, 'before': '<a id="git-guardrails-claude-code--авто"></a>\n', 'after': ''}, {'start': 17655, 'end': 17655, 'before': '<a id="setup-pre-commit--авто"></a>\n', 'after': ''}, {'start': 18055, 'end': 18055, 'before': '<a id="pr--авто"></a>\n', 'after': ''}, {'start': 18532, 'end': 18532, 'before': '<a id="5-crg--навігація-по-графу-коду-від-code-review-graph-mcp"></a>\n', 'after': ''}, {'start': 18598, 'end': 18598, 'before': '<a id="crg-explore-codebase--авто"></a>\n', 'after': ''}, {'start': 18916, 'end': 18916, 'before': '<a id="crg-debug-issue--авто"></a>\n', 'after': ''}, {'start': 19184, 'end': 19184, 'before': '<a id="crg-refactor-safely--авто"></a>\n', 'after': ''}, {'start': 19525, 'end': 19525, 'before': '<a id="crg-review-changes--авто"></a>\n', 'after': ''}, {'start': 19818, 'end': 19818, 'before': '<a id="6-прототипування-навчання-передача-контексту"></a>\n', 'after': ''}, {'start': 19886, 'end': 19946, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 20344, 'end': 20344, 'before': '<a id="frontend-design--авто--не-pocock--форк-anthropicsskills"></a>\n', 'after': ''}, {'start': 22297, 'end': 22297, 'before': '<a id="research--авто--не-плутай-з-deep-research-див-примітку-нижче"></a>\n', 'after': ''}, {'start': 22904, 'end': 22961, 'before': 'вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску', 'after': 'built-in-harness-skills-ship-with-claude-code-not-on-disk'}, {'start': 23396, 'end': 23456, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 23802, 'end': 23862, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 24234, 'end': 24294, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 24951, 'end': 24951, 'before': '<a id="7-утиліти-міграції-метаскіли"></a>\n', 'after': ''}, {'start': 24997, 'end': 24997, 'before': '<a id="migrate-to-shoehorn--авто"></a>\n', 'after': ''}, {'start': 25380, 'end': 25380, 'before': '<a id="scaffold-exercises--авто"></a>\n', 'after': ''}, {'start': 25778, 'end': 25778, 'before': '<a id="writing-for-agents--авто"></a>\n', 'after': ''}, {'start': 26454, 'end': 26454, 'before': '<a id="wizard--авто"></a>\n', 'after': ''}, {'start': 27191, 'end': 27251, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 27614, 'end': 27674, 'before': '`/команда`', 'after': 'command\n\nOriginal command-category placeholder: `/команда`.\n'}, {'start': 28100, 'end': 28100, 'before': '<a id="caveman--авто"></a>\n', 'after': ''}, {'start': 28429, 'end': 28429, 'before': '<a id="-конвеєр-ai-factory-власні-скіли-не-pocock"></a>\n', 'after': ''}, {'start': 29628, 'end': 29628, 'before': '<a id="repo-bootstrap--авто"></a>\n', 'after': ''}, {'start': 30310, 'end': 30310, 'before': '<a id="cto-research--авто"></a>\n', 'after': ''}, {'start': 30861, 'end': 30861, 'before': '<a id="cto-agenda--авто"></a>\n', 'after': ''}, {'start': 31415, 'end': 31415, 'before': '<a id="spec-flow--авто"></a>\n', 'after': ''}, {'start': 31992, 'end': 31992, 'before': '<a id="plan-critique--авто"></a>\n', 'after': ''}, {'start': 32535, 'end': 32535, 'before': '<a id="plan-defense--авто"></a>\n', 'after': ''}, {'start': 32994, 'end': 32994, 'before': '<a id="acceptance-spec--авто"></a>\n', 'after': ''}, {'start': 33530, 'end': 33530, 'before': '<a id="ship-report--авто"></a>\n', 'after': ''}, {'start': 34225, 'end': 34225, 'before': '<a id="post-deploy-check--авто"></a>\n', 'after': ''}, {'start': 35008, 'end': 35008, 'before': '<a id="антипатерни-"></a>\n', 'after': ''}, {'start': 35650, 'end': 35650, 'before': '<a id="-ponytail--режим-лінивого-сеньйора-6-скілів-не-pocock"></a>\n', 'after': ''}, {'start': 37224, 'end': 37224, 'before': '<a id="ponytail--авто-режим-тримається-до-кінця-сесії"></a>\n', 'after': ''}, {'start': 38375, 'end': 38375, 'before': '<a id="ponytail-review--авто"></a>\n', 'after': ''}, {'start': 39307, 'end': 39307, 'before': '<a id="ponytail-audit--авто"></a>\n', 'after': ''}, {'start': 40172, 'end': 40172, 'before': '<a id="ponytail-debt--авто"></a>\n', 'after': ''}, {'start': 41104, 'end': 41104, 'before': '<a id="ponytail-gain--авто-разова-картка"></a>\n', 'after': ''}, {'start': 42314, 'end': 42314, 'before': '<a id="ponytail-help--авто-разова-картка"></a>\n', 'after': ''}, {'start': 42868, 'end': 42868, 'before': '<a id="комбо-з-рештою-сховища"></a>\n', 'after': ''}, {'start': 44055, 'end': 44055, 'before': '<a id="антипатерни--1"></a>\n', 'after': ''}, {'start': 44936, 'end': 44936, 'before': '<a id="-звязки-скілів-комбо-для-кращого-результату"></a>\n', 'after': ''}, {'start': 45354, 'end': 45396, 'before': 'скіл--mcp-комбо-для-кращого-результату', 'after': 'skill--mcp-combinations-for-better-results'}, {'start': 45442, 'end': 45442, 'before': '<a id="планування--доставка"></a>\n', 'after': ''}, {'start': 45466, 'end': 45466, 'before': '<a id="grilling--ядро-інтервю-лупа-смикається-зсередини-інших-скілів"></a>\n', 'after': ''}, {'start': 47342, 'end': 47342, 'before': '<a id="grill-me--to-spec--to-tickets--implement--флагманський-рецепт-доставки-фічі"></a>\n', 'after': ''}, {'start': 48852, 'end': 48852, 'before': '<a id="wayfinder--to-tickets-по-кожному-investigation-тікету-коли-фіча-завелика-для-одної-сесії"></a>\n', 'after': ''}, {'start': 51910, 'end': 51910, 'before': '<a id="research--grill-with-docs--domain-modeling-коли-рішення-залежить-від-незнайомого-apiдоки"></a>\n', 'after': ''}, {'start': 53569, 'end': 53569, 'before': '<a id="дизайн--архітектура"></a>\n', 'after': ''}, {'start': 53595, 'end': 53595, 'before': '<a id="improve-codebase-architecture--codebase-design--grill-me--флагманський-рецепт-рефакторингу"></a>\n', 'after': ''}, {'start': 57322, 'end': 57322, 'before': '<a id="баги--якість"></a>\n', 'after': ''}, {'start': 58516, 'end': 58516, 'before': '<a id="tdd--code-review-skill-перед-mergepr--стандарти--spec"></a>\n', 'after': ''}, {'start': 59771, 'end': 59771, 'before': '<a id="code-review--code-review--crg-review-changes--receiving-code-review-після-ревю--як-реагувати-на-фідбек"></a>\n', 'after': ''}, {'start': 62302, 'end': 62302, 'before': '<a id="crg-refactor-safely--tdd--або-resolving-merge-conflicts--tdd"></a>\n', 'after': ''}, {'start': 64068, 'end': 64068, 'before': '<a id="чистка--дублі--зламана-логіка--стилі--motion"></a>\n', 'after': ''}, {'start': 66944, 'end': 66944, 'before': '<a id="вхідні--процес"></a>\n', 'after': ''}, {'start': 66965, 'end': 66965, 'before': '<a id="setup-matt-pocock-skills--усі-engineering-скіли"></a>\n', 'after': ''}, {'start': 68932, 'end': 68932, 'before': '<a id="мета-обгортки"></a>\n', 'after': ''}, {'start': 69135, 'end': 69135, 'before': '<a id="міграція--парність-legacy--new"></a>\n', 'after': ''}, {'start': 69173, 'end': 69173, 'before': '<a id="legacy--new-parity--аудит--gap--порт--звірка"></a>\n', 'after': ''}, {'start': 71840, 'end': 71881, 'before': 'чистка--дублі--зламана-логіка--стилі', 'after': 'cleanup--duplicates--broken-logic--styles'}, {'start': 72271, 'end': 72271, 'before': '<a id="-скіл--mcp-комбо-для-кращого-результату"></a>\n', 'after': ''}, {'start': 72536, 'end': 72536, 'before': '<a id="кодинг-із-актуальною-докою"></a>\n', 'after': ''}, {'start': 73669, 'end': 73669, 'before': '<a id="візуальний--браузерний-dev-loop"></a>\n', 'after': ''}, {'start': 74276, 'end': 74276, 'before': '<a id="diagnosing-bugs--playwright--chrome-devtools-mcp_docker--плагін"></a>\n', 'after': ''}, {'start': 75397, 'end': 75397, 'before': '<a id="дизайн--код"></a>\n', 'after': ''}, {'start': 75416, 'end': 75416, 'before': '<a id="prototype--дизайн-задачі--figma-desktop-mcp"></a>\n', 'after': ''}, {'start': 76442, 'end': 76442, 'before': '<a id="навігація--архітектура-великого-кодбейзу"></a>\n', 'after': ''}, {'start': 77873, 'end': 77873, 'before': '<a id="-mcp-сервери-на-машині"></a>\n', 'after': ''}, {'start': 78096, 'end': 78096, 'before': '<a id="спільні-mcp-є-і-в-claude-і-в-cursor"></a>\n', 'after': ''}, {'start': 79175, 'end': 79175, 'before': '<a id="figma-desktop-локальний-1270013845mcp"></a>\n', 'after': ''}, {'start': 79674, 'end': 79674, 'before': '<a id="code-review-graph-локальний-бінар-привязаний-до-cassiopeia-admin-ui"></a>\n', 'after': ''}, {'start': 80247, 'end': 80247, 'before': '<a id="тільки-claude"></a>\n', 'after': ''}, {'start': 80263, 'end': 80263, 'before': '<a id="figma-плагін-figma-remote-mcpfigmacommcp"></a>\n', 'after': ''}, {'start': 80421, 'end': 80452, 'before': 'плагінні--вбудовані-скіли-поза', 'after': 'plugin--built-in-skills-outside'}, {'start': 80846, 'end': 80846, 'before': '<a id="chrome-devtools-плагін-figma-friend-також-проєкт-cargodes"></a>\n', 'after': ''}, {'start': 81289, 'end': 81289, 'before': '<a id="тільки-cursor"></a>\n', 'after': ''}, {'start': 81429, 'end': 81429, 'before': '<a id="-плагінні--вбудовані-скіли-поза-agentsskills"></a>\n', 'after': ''}, {'start': 81637, 'end': 81637, 'before': '<a id="плагінні-скіли-з-claudeplugins-керуються-маркетплейсом"></a>\n', 'after': ''}, {'start': 81712, 'end': 81712, 'before': '<a id="плагін-figma-friend-v001-marketplace-figma-friend"></a>\n', 'after': ''}, {'start': 82241, 'end': 82241, 'before': '<a id="плагін-figma-офіційний-v2260"></a>\n', 'after': ''}, {'start': 84035, 'end': 84035, 'before': '<a id="вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску"></a>\n', 'after': ''}, {'start': 86527, 'end': 86527, 'before': '<a id="-наскрізні-сценарії-end-to-end-промти"></a>\n', 'after': ''}, {'start': 86695, 'end': 86695, 'before': '<a id="1-нова-фіча-від-нуля-до-pr"></a>\n', 'after': ''}, {'start': 87215, 'end': 87215, 'before': '<a id="2-архітектурний-рефактор-флагман-"></a>\n', 'after': ''}, {'start': 87765, 'end': 87765, 'before': '<a id="3-складний-рантайм-баг"></a>\n', 'after': ''}, {'start': 88165, 'end': 88165, 'before': '<a id="4-ui-з-макета-до-робочого-екрана"></a>\n', 'after': ''}, {'start': 88568, 'end': 88568, 'before': '<a id="5-розгрібання-вхідного-потоку"></a>\n', 'after': ''}, {'start': 88829, 'end': 88829, 'before': '<a id="6-дослідження-незнайомої-технології--рішення-в-adr"></a>\n', 'after': ''}, {'start': 89190, 'end': 89190, 'before': '<a id="7-перенесення-legacy-функціоналу-на-нові-компоненти"></a>\n', 'after': ''}, {'start': 89967, 'end': 89967, 'before': '<a id="8-чистка-дублі--зламана-логіка--стилі--анімації"></a>\n', 'after': ''}, {'start': 90794, 'end': 90794, 'before': '<a id="9-merge-коректне-вирішення-конфліктів--фікс-зламаного-алгоритму"></a>\n', 'after': ''}, {'start': 91638, 'end': 91679, 'before': 'чистка--дублі--зламана-логіка--стилі', 'after': 'cleanup--duplicates--broken-logic--styles'}, {'start': 91693, 'end': 91693, 'before': '<a id="10-pull-коректне-вирішення-конфліктів--фікс-зламаного-алгоритму"></a>\n', 'after': ''}, {'start': 92671, 'end': 92712, 'before': 'чистка--дублі--зламана-логіка--стилі', 'after': 'cleanup--duplicates--broken-logic--styles'}, {'start': 92725, 'end': 92725, 'before': '<a id="11-реліз-готовність-security-review-перед-релізом"></a>\n', 'after': ''}, {'start': 93451, 'end': 93451, 'before': '<a id="12-завершення-сесії"></a>\n', 'after': ''}, {'start': 93607, 'end': 93607, 'before': '<a id="-ревю-пас-що-перевіряє-себе-як-отримувати-щоразу"></a>\n', 'after': ''}, {'start': 94218, 'end': 94218, 'before': '<a id="словник-без-нього-розділ-не-читається"></a>\n', 'after': ''}, {'start': 96638, 'end': 96638, 'before': '<a id="6-інваріантів"></a>\n', 'after': ''}, {'start': 98317, 'end': 98317, 'before': '<a id="кошики-findings"></a>\n', 'after': ''}, {'start': 98647, 'end': 98647, 'before': '<a id="промт-копіпаст"></a>\n', 'after': ''}, {'start': 99360, 'end': 99360, 'before': '<a id="definition-of-done-для-workerа-щоб-пас-був-дешевим"></a>\n', 'after': ''}, {'start': 99742, 'end': 99742, 'before': '<a id="базлайни--у-файл-не-в-голову"></a>\n', 'after': ''}, {'start': 100076, 'end': 100076, 'before': '<a id="ціна-і-що-різати"></a>\n', 'after': ''}, {'start': 100395, 'end': 100395, 'before': '<a id="звязки"></a>\n', 'after': ''}, {'start': 101054, 'end': 101054, 'before': '<a id="-як-скіл-влаштований-під-капотом"></a>\n', 'after': ''}, {'start': 102804, 'end': 102804, 'before': '<a id="-обслуговування"></a>\n', 'after': ''}, {'start': 108723, 'end': 108723, 'before': '<a id="збереження-локальних-виправлень-2026-10-14"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="-шпаргалка-по-скілах-agentsskills"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 1, 'record': {'text': '<a id="як-викликаються-скіли"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 2, 'record': {'text': '<a id="ui-рекомендована-точка-входу"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 3, 'record': {'text': '<a id="-зміст"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 4, 'record': {'text': '<a id="1-планування-й-узгодження-grilling--роутинг"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 5, 'record': {'text': '<a id="grilling--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 6, 'record': {'text': '<a id="2-вимоги--задачі--реалізація"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 7, 'record': {'text': '<a id="3-архітектура-дизайн-і-якість-коду"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 8, 'record': {'text': '<a id="codebase-design--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 9, 'record': {'text': '<a id="domain-modeling--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 10, 'record': {'text': '<a id="tdd--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 11, 'record': {'text': '<a id="diagnosing-bugs--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 12, 'record': {'text': '<a id="code-review--авто--колізія-назви--див-примітку-нижче"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 13, 'record': {'text': '<a id="receiving-code-review--авто--не-pocock--з-obrasuperpowers"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 14, 'record': {'text': '<a id="4-git-merge-і-запобіжники"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 15, 'record': {'text': '<a id="resolving-merge-conflicts--авто--апстрім-прибрав-2026-09-24-тут-лишили-як-кастомний"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 16, 'record': {'text': '<a id="git-guardrails-claude-code--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 17, 'record': {'text': '<a id="setup-pre-commit--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 18, 'record': {'text': '<a id="pr--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 19, 'record': {'text': '<a id="5-crg--навігація-по-графу-коду-від-code-review-graph-mcp"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 20, 'record': {'text': '<a id="crg-explore-codebase--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 21, 'record': {'text': '<a id="crg-debug-issue--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 22, 'record': {'text': '<a id="crg-refactor-safely--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 23, 'record': {'text': '<a id="crg-review-changes--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 24, 'record': {'text': '<a id="6-прототипування-навчання-передача-контексту"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 25, 'record': {'text': '<a id="frontend-design--авто--не-pocock--форк-anthropicsskills"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 26, 'record': {'text': '<a id="research--авто--не-плутай-з-deep-research-див-примітку-нижче"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 27, 'record': {'text': '<a id="7-утиліти-міграції-метаскіли"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 28, 'record': {'text': '<a id="migrate-to-shoehorn--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 29, 'record': {'text': '<a id="scaffold-exercises--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 30, 'record': {'text': '<a id="writing-for-agents--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 31, 'record': {'text': '<a id="wizard--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 32, 'record': {'text': '<a id="caveman--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 33, 'record': {'text': '<a id="-конвеєр-ai-factory-власні-скіли-не-pocock"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 34, 'record': {'text': '<a id="repo-bootstrap--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 35, 'record': {'text': '<a id="cto-research--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 36, 'record': {'text': '<a id="cto-agenda--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 37, 'record': {'text': '<a id="spec-flow--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 38, 'record': {'text': '<a id="plan-critique--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 39, 'record': {'text': '<a id="plan-defense--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 40, 'record': {'text': '<a id="acceptance-spec--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 41, 'record': {'text': '<a id="ship-report--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 42, 'record': {'text': '<a id="post-deploy-check--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 43, 'record': {'text': '<a id="антипатерни-"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 44, 'record': {'text': '<a id="-ponytail--режим-лінивого-сеньйора-6-скілів-не-pocock"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 45, 'record': {'text': '<a id="ponytail--авто-режим-тримається-до-кінця-сесії"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 46, 'record': {'text': '<a id="ponytail-review--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 47, 'record': {'text': '<a id="ponytail-audit--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 48, 'record': {'text': '<a id="ponytail-debt--авто"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 49, 'record': {'text': '<a id="ponytail-gain--авто-разова-картка"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 50, 'record': {'text': '<a id="ponytail-help--авто-разова-картка"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 51, 'record': {'text': '<a id="комбо-з-рештою-сховища"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 52, 'record': {'text': '<a id="антипатерни--1"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 53, 'record': {'text': '<a id="-звязки-скілів-комбо-для-кращого-результату"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 54, 'record': {'text': '<a id="планування--доставка"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 55, 'record': {'text': '<a id="grilling--ядро-інтервю-лупа-смикається-зсередини-інших-скілів"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 56, 'record': {'text': '<a id="grill-me--to-spec--to-tickets--implement--флагманський-рецепт-доставки-фічі"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 57, 'record': {'text': '<a id="wayfinder--to-tickets-по-кожному-investigation-тікету-коли-фіча-завелика-для-одної-сесії"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 58, 'record': {'text': '<a id="research--grill-with-docs--domain-modeling-коли-рішення-залежить-від-незнайомого-apiдоки"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 59, 'record': {'text': '<a id="дизайн--архітектура"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 60, 'record': {'text': '<a id="improve-codebase-architecture--codebase-design--grill-me--флагманський-рецепт-рефакторингу"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 61, 'record': {'text': '<a id="баги--якість"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 62, 'record': {'text': '<a id="tdd--code-review-skill-перед-mergepr--стандарти--spec"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 63, 'record': {'text': '<a id="code-review--code-review--crg-review-changes--receiving-code-review-після-ревю--як-реагувати-на-фідбек"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 64, 'record': {'text': '<a id="crg-refactor-safely--tdd--або-resolving-merge-conflicts--tdd"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 65, 'record': {'text': '<a id="чистка--дублі--зламана-логіка--стилі--motion"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 66, 'record': {'text': '<a id="вхідні--процес"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 67, 'record': {'text': '<a id="setup-matt-pocock-skills--усі-engineering-скіли"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 68, 'record': {'text': '<a id="мета-обгортки"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 69, 'record': {'text': '<a id="міграція--парність-legacy--new"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 70, 'record': {'text': '<a id="legacy--new-parity--аудит--gap--порт--звірка"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 71, 'record': {'text': '<a id="-скіл--mcp-комбо-для-кращого-результату"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 72, 'record': {'text': '<a id="кодинг-із-актуальною-докою"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 73, 'record': {'text': '<a id="візуальний--браузерний-dev-loop"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 74, 'record': {'text': '<a id="diagnosing-bugs--playwright--chrome-devtools-mcp_docker--плагін"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 75, 'record': {'text': '<a id="дизайн--код"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 76, 'record': {'text': '<a id="prototype--дизайн-задачі--figma-desktop-mcp"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 77, 'record': {'text': '<a id="навігація--архітектура-великого-кодбейзу"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 78, 'record': {'text': '<a id="-mcp-сервери-на-машині"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 79, 'record': {'text': '<a id="спільні-mcp-є-і-в-claude-і-в-cursor"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 80, 'record': {'text': '<a id="figma-desktop-локальний-1270013845mcp"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 81, 'record': {'text': '<a id="code-review-graph-локальний-бінар-привязаний-до-cassiopeia-admin-ui"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 82, 'record': {'text': '<a id="тільки-claude"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 83, 'record': {'text': '<a id="figma-плагін-figma-remote-mcpfigmacommcp"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 84, 'record': {'text': '<a id="chrome-devtools-плагін-figma-friend-також-проєкт-cargodes"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 85, 'record': {'text': '<a id="тільки-cursor"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 86, 'record': {'text': '<a id="-плагінні--вбудовані-скіли-поза-agentsskills"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 87, 'record': {'text': '<a id="плагінні-скіли-з-claudeplugins-керуються-маркетплейсом"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 88, 'record': {'text': '<a id="плагін-figma-friend-v001-marketplace-figma-friend"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 89, 'record': {'text': '<a id="плагін-figma-офіційний-v2260"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 90, 'record': {'text': '<a id="вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 91, 'record': {'text': '<a id="-наскрізні-сценарії-end-to-end-промти"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 92, 'record': {'text': '<a id="1-нова-фіча-від-нуля-до-pr"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 93, 'record': {'text': '<a id="2-архітектурний-рефактор-флагман-"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 94, 'record': {'text': '<a id="3-складний-рантайм-баг"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 95, 'record': {'text': '<a id="4-ui-з-макета-до-робочого-екрана"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 96, 'record': {'text': '<a id="5-розгрібання-вхідного-потоку"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 97, 'record': {'text': '<a id="6-дослідження-незнайомої-технології--рішення-в-adr"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 98, 'record': {'text': '<a id="7-перенесення-legacy-функціоналу-на-нові-компоненти"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 99, 'record': {'text': '<a id="8-чистка-дублі--зламана-логіка--стилі--анімації"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 100, 'record': {'text': '<a id="9-merge-коректне-вирішення-конфліктів--фікс-зламаного-алгоритму"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 101, 'record': {'text': '<a id="10-pull-коректне-вирішення-конфліктів--фікс-зламаного-алгоритму"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 102, 'record': {'text': '<a id="11-реліз-готовність-security-review-перед-релізом"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 103, 'record': {'text': '<a id="12-завершення-сесії"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 104, 'record': {'text': '<a id="-ревю-пас-що-перевіряє-себе-як-отримувати-щоразу"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 105, 'record': {'text': '<a id="словник-без-нього-розділ-не-читається"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 106, 'record': {'text': '<a id="6-інваріантів"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 107, 'record': {'text': '<a id="кошики-findings"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 108, 'record': {'text': '<a id="промт-копіпаст"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 109, 'record': {'text': '<a id="definition-of-done-для-workerа-щоб-пас-був-дешевим"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 110, 'record': {'text': '<a id="базлайни--у-файл-не-в-голову"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 111, 'record': {'text': '<a id="ціна-і-що-різати"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 112, 'record': {'text': '<a id="звязки"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 113, 'record': {'text': '<a id="-як-скіл-влаштований-під-капотом"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 114, 'record': {'text': '<a id="-обслуговування"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 115, 'record': {'text': '<a id="збереження-локальних-виправлень-2026-10-14"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 127, 'record': {'text': '#-mcp-сервери-на-машині', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 128, 'record': {'text': '#-ponytail--режим-лінивого-сеньйора-6-скілів-не-pocock', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 129, 'record': {'text': '#-звязки-скілів-комбо-для-кращого-результату', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 130, 'record': {'text': '#-конвеєр-ai-factory-власні-скіли-не-pocock', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 131, 'record': {'text': '#-наскрізні-сценарії-end-to-end-промти', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 132, 'record': {'text': '#-обслуговування', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 133, 'record': {'text': '#-плагінні--вбудовані-скіли-поза-agentsskills', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 134, 'record': {'text': '#-ревю-пас-що-перевіряє-себе-як-отримувати-щоразу', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 135, 'record': {'text': '#-скіл--mcp-комбо-для-кращого-результату', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 136, 'record': {'text': '#-як-скіл-влаштований-під-капотом', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 137, 'record': {'text': '#1-планування-й-узгодження-grilling--роутинг', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 138, 'record': {'text': '#2-вимоги--задачі--реалізація', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 139, 'record': {'text': '#3-архітектура-дизайн-і-якість-коду', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 140, 'record': {'text': '#4-git-merge-і-запобіжники', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 141, 'record': {'text': '#5-crg--навігація-по-графу-коду-від-code-review-graph-mcp', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 142, 'record': {'text': '#6-прототипування-навчання-передача-контексту', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 143, 'record': {'text': '#7-утиліти-міграції-метаскіли', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 144, 'record': {'text': '#баги--якість', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 145, 'record': {'text': '#вбудовані-harness-скіли-ідуть-із-claude-code-не-на-диску', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 146, 'record': {'text': '#вхідні--процес', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 147, 'record': {'text': '#дизайн--архітектура', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 148, 'record': {'text': '#міграція--парність-legacy--new', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 149, 'record': {'text': '#плагінні-скіли-з-claudeplugins-керуються-маркетплейсом', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 150, 'record': {'text': '#планування--доставка', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 151, 'record': {'text': '#спільні-mcp-є-і-в-claude-і-в-cursor', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 152, 'record': {'text': '#тільки-claude', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 153, 'record': {'text': '#тільки-cursor', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 154, 'record': {'text': '#чистка--дублі--зламана-логіка--стилі--motion', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}, {'index': 155, 'record': {'text': '#як-викликаються-скіли', 'reason': 'Original intra-document fragment destination; preserved for parent-generated historical heading anchor compatibility. Not untranslated prose.'}}], 'pre_literals_sha256': '5dc61336104a7dcc2271852962035748ca532637e14710b43b55502538a703d7', 'current_literals_sha256': '41d54947774d3182d3308246226354fdda0df13a31ce0062246998b4ad40bd4d'},
    'docs/translations/en/docs/legacy/starter-readme.md': {'path': 'docs/translations/en/docs/legacy/starter-readme.md', 'pre_anchor_sha256': '783e53c9cde34693e962df0ccea920424638aefa2fbaac900c292ce7771f7c72', 'current_sha256': '4f6f408a0c6e200c4c7132bda6e2e8511a8283672c15b03b64d451ca1fbc3d67', 'removed_ids': [{'old_id': 'почати-тут', 'new_id': 'start-here', 'binding': 'Start here', 'line': 7}], 'changed_targets': [], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [], 'hunks': [{'start': 470, 'end': 616, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 872, 'end': 872, 'before': '<a id="почати-тут"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="почати-тут"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}], 'pre_literals_sha256': 'ad81da00c499ff2cf38bba9984727ef0249b6cf23bf5383b9ab7073518491c7e', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'docs/translations/en/rules/agent-stream-to-file.md': {'path': 'docs/translations/en/rules/agent-stream-to-file.md', 'pre_anchor_sha256': '8dda14c8b9acacaad6946e77b44966620a1453f36f209e0c8171c46fc8f3f9e8', 'current_sha256': 'ab6f2f6fb778c719a5d5a94ef01cb9769ccfd9022c487421032c37f72d891070', 'removed_ids': [{'old_id': '1-навіщо--і-чому-наявного-транскрипту-не-досить', 'new_id': '1-why--and-why-the-existing-transcript-is-not-enough', 'binding': '1. Why — and why the existing transcript is not enough', 'line': 14}, {'old_id': '2-правило', 'new_id': '2-the-rule', 'binding': '2. The rule', 'line': 47}, {'old_id': '3-що-робить-оркестратор', 'new_id': '3-what-the-orchestrator-does', 'binding': '3. What the orchestrator does', 'line': 89}, {'old_id': '4-кому-це-найпотрібніше', 'new_id': '4-who-needs-this-most', 'binding': '4. Who needs this most', 'line': 106}, {'old_id': '5-межі', 'new_id': '5-limits', 'binding': '5. Limits', 'line': 119}, {'old_id': '-повязане', 'new_id': '-related', 'binding': '🔗 Related', 'line': 135}], 'changed_targets': [], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [], 'hunks': [{'start': 599, 'end': 745, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 959, 'end': 959, 'before': '<a id="1-навіщо--і-чому-наявного-транскрипту-не-досить"></a>\n', 'after': ''}, {'start': 2915, 'end': 2915, 'before': '<a id="2-правило"></a>\n', 'after': ''}, {'start': 4809, 'end': 4809, 'before': '<a id="3-що-робить-оркестратор"></a>\n', 'after': ''}, {'start': 5722, 'end': 5722, 'before': '<a id="4-кому-це-найпотрібніше"></a>\n', 'after': ''}, {'start': 6245, 'end': 6245, 'before': '<a id="5-межі"></a>\n', 'after': ''}, {'start': 7245, 'end': 7245, 'before': '<a id="-повязане"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="1-навіщо--і-чому-наявного-транскрипту-не-досить"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 1, 'record': {'text': '<a id="2-правило"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 2, 'record': {'text': '<a id="3-що-робить-оркестратор"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 3, 'record': {'text': '<a id="4-кому-це-найпотрібніше"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 4, 'record': {'text': '<a id="5-межі"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 5, 'record': {'text': '<a id="-повязане"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}], 'pre_literals_sha256': '88666b9cc9a3802651c2d6551b9c0aeac8de835c4e16b993a80de013808396e5', 'current_literals_sha256': '56830107a57ed8e68c8a05408aea3c6685a5092778d6a19ef3b24fc1f5696c0b'},
    'docs/translations/en/rules/multi-model-roles.md': {'path': 'docs/translations/en/rules/multi-model-roles.md', 'pre_anchor_sha256': '12015fbfcca0d1cc8bab23acee55b56aab6e4ae7d2cd242cc242b03f17f54839', 'current_sha256': 'fa497533cabece506a9e3aba807d3674d5e1eada8f9fef40e9a4f4a4d72ab0c6', 'removed_ids': [{'old_id': '0-хто-і-коли-це-читає', 'new_id': '0-who-reads-this-and-when', 'binding': '0. Who reads this and when', 'line': 13}, {'old_id': '1-що-реально-доступно', 'new_id': '1-what-is-actually-available', 'binding': '1. What is actually available', 'line': 23}, {'old_id': '2-розкладка-ролей', 'new_id': '2-role-allocation', 'binding': '2. Role allocation', 'line': 46}, {'old_id': '21-коли-потрібного-тіра-немає', 'new_id': '21-when-the-required-tier-is-unavailable', 'binding': '2.1 When the required tier is unavailable', 'line': 65}, {'old_id': '22-критика-чотири-лінзи-дорогим-тіром--найдорожчий-рядок-конвеєра', 'new_id': '22-critique-four-lenses-on-an-expensive-tier--the-pipelines-most-expensive-row', 'binding': "2.2 Critique: four lenses on an expensive tier — the pipeline's most expensive row", 'line': 80}, {'old_id': '3-правило-незалежності', 'new_id': '3-independence-rule', 'binding': '3. Independence rule', 'line': 142}, {'old_id': '4-коли-тір-не-має-значення', 'new_id': '4-when-tier-does-not-matter', 'binding': '4. When tier does not matter', 'line': 185}, {'old_id': '5-захист-plan-defense', 'new_id': '5-defense-plan-defense', 'binding': '5. Defense (plan-defense)', 'line': 193}, {'old_id': '-повязане', 'new_id': '-related', 'binding': '🔗 Related', 'line': 204}], 'changed_targets': [], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [], 'hunks': [{'start': 548, 'end': 694, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 941, 'end': 941, 'before': '<a id="0-хто-і-коли-це-читає"></a>\n', 'after': ''}, {'start': 1341, 'end': 1341, 'before': '<a id="1-що-реально-доступно"></a>\n', 'after': ''}, {'start': 2734, 'end': 2734, 'before': '<a id="2-розкладка-ролей"></a>\n', 'after': ''}, {'start': 4805, 'end': 4805, 'before': '<a id="21-коли-потрібного-тіра-немає"></a>\n', 'after': ''}, {'start': 5850, 'end': 5850, 'before': '<a id="22-критика-чотири-лінзи-дорогим-тіром--найдорожчий-рядок-конвеєра"></a>\n', 'after': ''}, {'start': 9882, 'end': 9882, 'before': '<a id="3-правило-незалежності"></a>\n', 'after': ''}, {'start': 13263, 'end': 13263, 'before': '<a id="4-коли-тір-не-має-значення"></a>\n', 'after': ''}, {'start': 13650, 'end': 13650, 'before': '<a id="5-захист-plan-defense"></a>\n', 'after': ''}, {'start': 15324, 'end': 15324, 'before': '<a id="-повязане"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="0-хто-і-коли-це-читає"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 1, 'record': {'text': '<a id="1-що-реально-доступно"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 2, 'record': {'text': '<a id="2-розкладка-ролей"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 3, 'record': {'text': '<a id="21-коли-потрібного-тіра-немає"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 4, 'record': {'text': '<a id="22-критика-чотири-лінзи-дорогим-тіром--найдорожчий-рядок-конвеєра"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 5, 'record': {'text': '<a id="3-правило-незалежності"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 6, 'record': {'text': '<a id="4-коли-тір-не-має-значення"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 7, 'record': {'text': '<a id="5-захист-plan-defense"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 8, 'record': {'text': '<a id="-повязане"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}], 'pre_literals_sha256': 'e7fa9fc660a2d2af802928490ba0d789343a1dd932f00cff00767ead9f0d7e62', 'current_literals_sha256': 'ef1e2a3b35b4073447955a5ce4abfa8a9344b4d703699f7f72df33003b0f1c95'},
    'docs/translations/en/rules/repo-standards-manifest.md': {'path': 'docs/translations/en/rules/repo-standards-manifest.md', 'pre_anchor_sha256': 'edd54eb4c46548d5499c5b3d6c99c5755b397ab35d71af64c615b92a93e42a7f', 'current_sha256': 'b5297c88836927f09826ca8ecb2ef63b2a2e2849430d7109dee36d447ba991f4', 'removed_ids': [{'old_id': '0-мова--перше-що-читається', 'new_id': '0-language-is-read-first', 'binding': '0. Language is read first', 'line': 20}, {'old_id': '1-фіксовані-заголовки', 'new_id': '1-fixed-headings', 'binding': '1. Fixed headings', 'line': 34}, {'old_id': '2-що-в-маніфест-не-кладеться', 'new_id': '2-what-does-not-go-into-the-manifest', 'binding': '2. What does not go into the manifest', 'line': 105}, {'old_id': '3-коли-маніфесту-немає', 'new_id': '3-when-the-manifest-is-absent', 'binding': '3. When the manifest is absent', 'line': 115}, {'old_id': '-повязане', 'new_id': '-related', 'binding': '🔗 Related', 'line': 122}], 'changed_targets': [], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [{'before': '### `## Мірник`\n', 'after': '### Yardstick\n\nOriginal manifest heading: `## Мірник`.\n', 'old_native_id': '-мірник', 'new_native_id': 'yardstick', 'preserved_body_literal': '## Мірник'}, {'before': '### `## Не мірник`\n', 'after': '### Not a yardstick\n\nOriginal manifest heading: `## Не мірник`.\n', 'old_native_id': '-не-мірник', 'new_native_id': 'not-a-yardstick', 'preserved_body_literal': '## Не мірник'}, {'before': '### `## Машинні гейти`\n', 'after': '### Machine gates\n\nOriginal manifest heading: `## Машинні гейти`.\n', 'old_native_id': '-машинні-гейти', 'new_native_id': 'machine-gates', 'preserved_body_literal': '## Машинні гейти'}, {'before': '### `## Конституція`\n', 'after': '### Constitution\n\nOriginal manifest heading: `## Конституція`.\n', 'old_native_id': '-конституція', 'new_native_id': 'constitution', 'preserved_body_literal': '## Конституція'}, {'before': '### `## Поріг пайплайна`\n', 'after': '### Pipeline threshold\n\nOriginal manifest heading: `## Поріг пайплайна`.\n', 'old_native_id': '-поріг-пайплайна', 'new_native_id': 'pipeline-threshold', 'preserved_body_literal': '## Поріг пайплайна'}, {'before': '### `## Розміщення`\n', 'after': '### Placement\n\nOriginal manifest heading: `## Розміщення`.\n', 'old_native_id': '-розміщення', 'new_native_id': 'placement', 'preserved_body_literal': '## Розміщення'}, {'before': '### `## Гілки й PR`\n', 'after': '### Branches and PRs\n\nOriginal manifest heading: `## Гілки й PR`.\n', 'old_native_id': '-гілки-й-pr', 'new_native_id': 'branches-and-prs', 'preserved_body_literal': '## Гілки й PR'}, {'before': '### `## Артефакти`\n', 'after': '### Artifacts\n\nOriginal manifest heading: `## Артефакти`.\n', 'old_native_id': '-артефакти', 'new_native_id': 'artifacts', 'preserved_body_literal': '## Артефакти'}], 'hunks': [{'start': 564, 'end': 710, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 1365, 'end': 1365, 'before': '<a id="0-мова--перше-що-читається"></a>\n', 'after': ''}, {'start': 1995, 'end': 1995, 'before': '<a id="1-фіксовані-заголовки"></a>\n', 'after': ''}, {'start': 2202, 'end': 2252, 'before': '`## Мірник`', 'after': 'Yardstick\n\nOriginal manifest heading: `## Мірник`.'}, {'start': 2427, 'end': 2486, 'before': '`## Не мірник`', 'after': 'Not a yardstick\n\nOriginal manifest heading: `## Не мірник`.'}, {'start': 2656, 'end': 2717, 'before': '`## Машинні гейти`', 'after': 'Machine gates\n\nOriginal manifest heading: `## Машинні гейти`.'}, {'start': 3030, 'end': 3088, 'before': '`## Конституція`', 'after': 'Constitution\n\nOriginal manifest heading: `## Конституція`.'}, {'start': 3292, 'end': 3360, 'before': '`## Поріг пайплайна`', 'after': 'Pipeline threshold\n\nOriginal manifest heading: `## Поріг пайплайна`.'}, {'start': 3602, 'end': 3656, 'before': '`## Розміщення`', 'after': 'Placement\n\nOriginal manifest heading: `## Розміщення`.'}, {'start': 3760, 'end': 3821, 'before': '`## Гілки й PR`', 'after': 'Branches and PRs\n\nOriginal manifest heading: `## Гілки й PR`.'}, {'start': 3910, 'end': 3963, 'before': '`## Артефакти`', 'after': 'Artifacts\n\nOriginal manifest heading: `## Артефакти`.'}, {'start': 5384, 'end': 5384, 'before': '<a id="2-що-в-маніфест-не-кладеться"></a>\n', 'after': ''}, {'start': 5887, 'end': 5887, 'before': '<a id="3-коли-маніфесту-немає"></a>\n', 'after': ''}, {'start': 6160, 'end': 6160, 'before': '<a id="-повязане"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="0-мова--перше-що-читається"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 1, 'record': {'text': '<a id="1-фіксовані-заголовки"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 2, 'record': {'text': '<a id="2-що-в-маніфест-не-кладеться"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 3, 'record': {'text': '<a id="3-коли-маніфесту-немає"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 4, 'record': {'text': '<a id="-повязане"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}], 'pre_literals_sha256': '38c8cbf54e5319c371b3cd7379f9ad60ad1788654a90788e380af847e2ed68d6', 'current_literals_sha256': 'a19746b8ad3d553d38c63b44e3832e6ddda0f90bceb2be727a2f52c80b66791e'},
    'docs/translations/en/rules/typescript-pocock-idioms.md': {'path': 'docs/translations/en/rules/typescript-pocock-idioms.md', 'pre_anchor_sha256': '8c6c4fd55fc0ca751c04934bc64fdaec595137cec3bfe8eb619a4e205fc2e3cf', 'current_sha256': 'bdb969ed7f415b0b417e7f2f23c6328a1b3a4a697f2ec378ca89134cc3ce8137', 'removed_ids': [{'old_id': '-matt-pocock--totaltypescript--ідіоми', 'new_id': '-matt-pocock--totaltypescript--idioms', 'binding': '🧠 Matt Pocock / TotalTypeScript — idioms', 'line': 7}, {'old_id': '-type-system-ідіоми', 'new_id': '-type-system-idioms', 'binding': '🎯 Type-system idioms', 'line': 17}, {'old_id': '-архітектура--тести', 'new_id': '-architecture--tests', 'binding': '🏗️ Architecture / tests', 'line': 41}, {'old_id': '-застосовано-в-cassiopeia-admin-ui-house-decisions', 'new_id': '-applied-in-cassiopeia-admin-ui-house-decisions', 'binding': '📌 Applied in cassiopeia-admin-ui (house decisions)', 'line': 48}, {'old_id': '-повязане', 'new_id': '-related', 'binding': '🔗 Related', 'line': 55}], 'changed_targets': [], 'banner_changes': [{'before': 'Original-language compatibility anchors and literal protocol tokens remain where required.', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.'}], 'heading_changes': [], 'hunks': [{'start': 546, 'end': 692, 'before': 'Original-language compatibility anchors and literal protocol tokens remain where requir', 'after': 'Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retain'}, {'start': 697, 'end': 697, 'before': '<a id="-matt-pocock--totaltypescript--ідіоми"></a>\n', 'after': ''}, {'start': 1498, 'end': 1498, 'before': '<a id="-type-system-ідіоми"></a>\n', 'after': ''}, {'start': 4098, 'end': 4098, 'before': '<a id="-архітектура--тести"></a>\n', 'after': ''}, {'start': 4692, 'end': 4692, 'before': '<a id="-застосовано-в-cassiopeia-admin-ui-house-decisions"></a>\n', 'after': ''}, {'start': 5155, 'end': 5155, 'before': '<a id="-повязане"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="-matt-pocock--totaltypescript--ідіоми"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 1, 'record': {'text': '<a id="-type-system-ідіоми"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 2, 'record': {'text': '<a id="-архітектура--тести"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 3, 'record': {'text': '<a id="-застосовано-в-cassiopeia-admin-ui-house-decisions"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}, {'index': 4, 'record': {'text': '<a id="-повязане"></a>', 'reason': 'Explicit compatibility anchor preserving the original generated heading fragment after English translation; not display prose.'}}], 'pre_literals_sha256': '868cc4867f38c569ed62bd5db5c1f592fae7a392bf937ed11ac1bbf44ec52733', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'skills/anti-slop-design/SKILL.md': {'path': 'skills/anti-slop-design/SKILL.md', 'pre_anchor_sha256': '30b435735135e9932e7eca10f99e37012ef08f8ed13f93ff2b751d558b12f38a', 'current_sha256': '79bb55e04736785bdc2e52dc4edcbeb435ed0c263edd22f192b2d891a71aa550', 'removed_ids': [{'old_id': 'anti-slop-design--каталог-ai-tells--гейт', 'new_id': 'anti-slop-design--ai-tell-catalog--gate', 'binding': 'anti-slop-design — AI-tell catalog + gate', 'line': 7}, {'old_id': '0-design-read--один-рядок-до-коду', 'new_id': '0-design-read--one-line-before-code', 'binding': '0. Design read — one line BEFORE code', 'line': 17}, {'old_id': '1-три-дилси', 'new_id': '1-three-dials', 'binding': '1. Three dials', 'line': 31}, {'old_id': '2-каталог-ai-tells-bias-correction', 'new_id': '2-ai-tell-catalog-bias-correction', 'binding': '2. AI-tell catalog (bias correction)', 'line': 55}, {'old_id': '21-типографіка', 'new_id': '21-typography', 'binding': '2.1 Typography', 'line': 61}, {'old_id': '22-колір', 'new_id': '22-color', 'binding': '2.2 Color', 'line': 70}, {'old_id': '23-лейаут', 'new_id': '23-layout', 'binding': '2.3 Layout', 'line': 79}, {'old_id': '24-матеріальність-і-декор', 'new_id': '24-materiality-and-decoration', 'binding': '2.4 Materiality and decoration', 'line': 88}, {'old_id': '25-копірайт-і-чесність-доказу', 'new_id': '25-copy-and-honest-evidence', 'binding': '2.5 Copy and honest evidence', 'line': 97}, {'old_id': '26-моушн', 'new_id': '26-motion', 'binding': '2.6 Motion', 'line': 105}, {'old_id': '27-вивід-і-залежності', 'new_id': '27-output-and-dependencies', 'binding': '2.7 Output and dependencies', 'line': 115}, {'old_id': '3-pre-flight-гейт-перед-готово', 'new_id': '3-pre-flight-gate-before-done', 'binding': '3. Pre-flight gate (before “done”)', 'line': 124}, {'old_id': '4-у-проєкті-факти-проєкту-перемагають-ці-дефолти', 'new_id': '4-in-a-project-project-facts-override-these-defaults', 'binding': '4. In a project: project facts override these defaults', 'line': 149}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 708, 'end': 708, 'before': '<a id="anti-slop-design--каталог-ai-tells--гейт"></a>\n', 'after': ''}, {'start': 1204, 'end': 1204, 'before': '<a id="0-design-read--один-рядок-до-коду"></a>\n', 'after': ''}, {'start': 1952, 'end': 1952, 'before': '<a id="1-три-дилси"></a>\n', 'after': ''}, {'start': 3090, 'end': 3090, 'before': '<a id="2-каталог-ai-tells-bias-correction"></a>\n', 'after': ''}, {'start': 3242, 'end': 3242, 'before': '<a id="21-типографіка"></a>\n', 'after': ''}, {'start': 4109, 'end': 4109, 'before': '<a id="22-колір"></a>\n', 'after': ''}, {'start': 5089, 'end': 5089, 'before': '<a id="23-лейаут"></a>\n', 'after': ''}, {'start': 5629, 'end': 5629, 'before': '<a id="24-матеріальність-і-декор"></a>\n', 'after': ''}, {'start': 6405, 'end': 6405, 'before': '<a id="25-копірайт-і-чесність-доказу"></a>\n', 'after': ''}, {'start': 7141, 'end': 7141, 'before': '<a id="26-моушн"></a>\n', 'after': ''}, {'start': 8100, 'end': 8100, 'before': '<a id="27-вивід-і-залежності"></a>\n', 'after': ''}, {'start': 8425, 'end': 8425, 'before': '<a id="3-pre-flight-гейт-перед-готово"></a>\n', 'after': ''}, {'start': 10220, 'end': 10220, 'before': '<a id="4-у-проєкті-факти-проєкту-перемагають-ці-дефолти"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="anti-slop-design--каталог-ai-tells--гейт"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="0-design-read--один-рядок-до-коду"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="1-три-дилси"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="2-каталог-ai-tells-bias-correction"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="21-типографіка"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="22-колір"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="23-лейаут"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 7, 'record': {'text': '<a id="24-матеріальність-і-декор"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 8, 'record': {'text': '<a id="25-копірайт-і-чесність-доказу"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 9, 'record': {'text': '<a id="26-моушн"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 10, 'record': {'text': '<a id="27-вивід-і-залежності"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 11, 'record': {'text': '<a id="3-pre-flight-гейт-перед-готово"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 12, 'record': {'text': '<a id="4-у-проєкті-факти-проєкту-перемагають-ці-дефолти"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': '6a8974f305696d28baca1dda8c8027b07c227c3dfdeed8affbfe910aba22e00c', 'current_literals_sha256': '6db2f0e9acc61f708c84734f9479f8e14c11158bf96f5f204ef144b79219c411'},
    'skills/deliver/spec-flow/SKILL.md': {'path': 'skills/deliver/spec-flow/SKILL.md', 'pre_anchor_sha256': '9513c3fe270dd3dadfb327a078cc0adb703841bd5f0224da780eaeb078f3ec97', 'current_sha256': '18b9dfe1a3bc99a9e531a65246a59ed32641884bc885b0ea85681fa69ac79ccf', 'removed_ids': [{'old_id': 'spec-flow--тонкий-sdd-оркестратор', 'new_id': 'spec-flow--a-thin-sdd-orchestrator', 'binding': 'spec-flow — a thin SDD orchestrator', 'line': 6}, {'old_id': '0-прочитати-маніфест', 'new_id': '0-read-the-manifest', 'binding': '0. Read the manifest', 'line': 20}, {'old_id': '2-specify--specmd-що--чому', 'new_id': '2-specify--specmd-what--why', 'binding': '2. specify → `spec.md` (WHAT / WHY)', 'line': 38}, {'old_id': '3-gate-1--спільне-розуміння', 'new_id': '3-gate-1--shared-understanding', 'binding': '3. GATE 1 — shared understanding', 'line': 45}, {'old_id': '4-plan--planmd-як', 'new_id': '4-plan--planmd-how', 'binding': '4. plan → `plan.md` (HOW)', 'line': 52}, {'old_id': '5-gate-2--критика-й-захист', 'new_id': '5-gate-2--critique-and-defense', 'binding': '5. GATE 2 — critique and defense', 'line': 65}, {'old_id': '7-implement--делегувати-tdd', 'new_id': '7-implement--delegate-tdd', 'binding': '7. implement → delegate `tdd`', 'line': 97}, {'old_id': '8-verify--делегувати-code-review', 'new_id': '8-verify--delegate-code-review', 'binding': '8. verify → delegate `code-review`', 'line': 104}, {'old_id': '9-wrap--делегувати-ship-report', 'new_id': '9-wrap--delegate-ship-report', 'binding': '9. wrap → delegate `ship-report`', 'line': 111}, {'old_id': 'делегування--не-переписуємо', 'new_id': 'delegation--do-not-rewrite', 'binding': 'Delegation — do NOT rewrite', 'line': 120}, {'old_id': 'завершення', 'new_id': 'completion', 'binding': 'Completion', 'line': 137}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 435, 'end': 435, 'before': '<a id="spec-flow--тонкий-sdd-оркестратор"></a>\n', 'after': ''}, {'start': 1049, 'end': 1049, 'before': '<a id="0-прочитати-маніфест"></a>\n', 'after': ''}, {'start': 2026, 'end': 2026, 'before': '<a id="2-specify--specmd-що--чому"></a>\n', 'after': ''}, {'start': 2240, 'end': 2240, 'before': '<a id="3-gate-1--спільне-розуміння"></a>\n', 'after': ''}, {'start': 2408, 'end': 2408, 'before': '<a id="4-plan--planmd-як"></a>\n', 'after': ''}, {'start': 3057, 'end': 3057, 'before': '<a id="5-gate-2--критика-й-захист"></a>\n', 'after': ''}, {'start': 4599, 'end': 4599, 'before': '<a id="7-implement--делегувати-tdd"></a>\n', 'after': ''}, {'start': 4922, 'end': 4922, 'before': '<a id="8-verify--делегувати-code-review"></a>\n', 'after': ''}, {'start': 5110, 'end': 5110, 'before': '<a id="9-wrap--делегувати-ship-report"></a>\n', 'after': ''}, {'start': 5306, 'end': 5306, 'before': '<a id="делегування--не-переписуємо"></a>\n', 'after': ''}, {'start': 6055, 'end': 6055, 'before': '<a id="завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="spec-flow--тонкий-sdd-оркестратор"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="0-прочитати-маніфест"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="2-specify--specmd-що--чому"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="3-gate-1--спільне-розуміння"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="4-plan--planmd-як"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="5-gate-2--критика-й-захист"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="7-implement--делегувати-tdd"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 7, 'record': {'text': '<a id="8-verify--делегувати-code-review"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 8, 'record': {'text': '<a id="9-wrap--делегувати-ship-report"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 9, 'record': {'text': '<a id="делегування--не-переписуємо"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 10, 'record': {'text': '<a id="завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': '98e2ee43387c37c1c4799eb95f2cc8105dced15309fc837e46b7f325912ac332', 'current_literals_sha256': '7ddd9757565cea971b8964f2a03b53c8e2a10faeb47c47cce22c3e5b37c14667'},
    'skills/design-pass/SKILL.md': {'path': 'skills/design-pass/SKILL.md', 'pre_anchor_sha256': 'c30fa82e4c2834d18e928a0521dfa8f9407af0316ebc00e5f18c4ccf7abb654e', 'current_sha256': '264e87dd2651551a9901f549dcbc30c28ba77ac31c95b85e58e2be319f736864', 'removed_ids': [{'old_id': 'design-pass--дизайн-реалізація-перевірка', 'new_id': 'design-pass--design-implementation-verification', 'binding': 'design-pass — design, implementation, verification', 'line': 6}, {'old_id': '1-спочатку-поточний-проєкт', 'new_id': '1-start-with-the-current-project', 'binding': '1. Start with the current project', 'line': 12}, {'old_id': '2-бриф-референс-і-план', 'new_id': '2-brief-reference-and-plan', 'binding': '2. Brief, reference and plan', 'line': 26}, {'old_id': '3-пріоритет-і-межі-загальних-правил', 'new_id': '3-priority-and-limits-of-general-rules', 'binding': '3. Priority and limits of general rules', 'line': 38}, {'old_id': '4-реалізуй-завершений-зріз', 'new_id': '4-implement-a-complete-slice', 'binding': '4. Implement a complete slice', 'line': 48}, {'old_id': '5-браузер--знахідки--виправлення--повторна-перевірка', 'new_id': '5-browser--findings--fixes--recheck', 'binding': '5. Browser → findings → fixes → recheck', 'line': 67}, {'old_id': '6-done-і-передача', 'new_id': '6-done-and-handoff', 'binding': '6. Done and handoff', 'line': 84}, {'old_id': 'використання-в-терміналі', 'new_id': 'terminal-usage', 'binding': 'Terminal usage', 'line': 100}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 380, 'end': 380, 'before': '<a id="design-pass--дизайн-реалізація-перевірка"></a>\n', 'after': ''}, {'start': 775, 'end': 775, 'before': '<a id="1-спочатку-поточний-проєкт"></a>\n', 'after': ''}, {'start': 1644, 'end': 1644, 'before': '<a id="2-бриф-референс-і-план"></a>\n', 'after': ''}, {'start': 3143, 'end': 3143, 'before': '<a id="3-пріоритет-і-межі-загальних-правил"></a>\n', 'after': ''}, {'start': 4241, 'end': 4241, 'before': '<a id="4-реалізуй-завершений-зріз"></a>\n', 'after': ''}, {'start': 6625, 'end': 6625, 'before': '<a id="5-браузер--знахідки--виправлення--повторна-перевірка"></a>\n', 'after': ''}, {'start': 9497, 'end': 9497, 'before': '<a id="6-done-і-передача"></a>\n', 'after': ''}, {'start': 11169, 'end': 11169, 'before': '<a id="використання-в-терміналі"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="design-pass--дизайн-реалізація-перевірка"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="1-спочатку-поточний-проєкт"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="2-бриф-референс-і-план"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="3-пріоритет-і-межі-загальних-правил"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="4-реалізуй-завершений-зріз"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="5-браузер--знахідки--виправлення--повторна-перевірка"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="6-done-і-передача"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 7, 'record': {'text': '<a id="використання-в-терміналі"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': '9b37271a329c43212d642ebb5b527e8f2517d284034269674d1a17f81237d565', 'current_literals_sha256': 'b49a07b1d95a0126d042f1035f731215982690527ee3559eb0afd04a74fae418'},
    'skills/design-pass/references/viewport-coverage.md': {'path': 'skills/design-pass/references/viewport-coverage.md', 'pre_anchor_sha256': 'acd275de5fe493507af9d50283cfcb406325a0a82a001cca3a87b3dee401f300', 'current_sha256': 'dba1e9c2f15b0cded329b9dfa4e337a2479bf0b4995d8225ab786f344ed42428', 'removed_ids': [{'old_id': 'viewport-coverage--спільний-контракт-ui', 'new_id': 'viewport-coverage--shared-ui-contract', 'binding': 'Viewport coverage — shared UI contract', 'line': 1}, {'old_id': 'масштаб-і-доступність--окремі-перевірки', 'new_id': 'scaling-and-accessibility--separate-checks', 'binding': 'Scaling and accessibility — separate checks', 'line': 20}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="viewport-coverage--спільний-контракт-ui"></a>\n', 'after': ''}, {'start': 1846, 'end': 1846, 'before': '<a id="масштаб-і-доступність--окремі-перевірки"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="viewport-coverage--спільний-контракт-ui"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="масштаб-і-доступність--окремі-перевірки"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'c936b3db312909b67c9d0f13fe742d8efb2e7bd0248c1e68a436beaf68fe27b5', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'skills/entity-e2e-coverage/SKILL.md': {'path': 'skills/entity-e2e-coverage/SKILL.md', 'pre_anchor_sha256': 'eb4e05ecf446cbbcf87fa1b48b42ada906931e7e6bf7c8aa901d673168ef0c32', 'current_sha256': '192e48d25309c8f8d5d30190beae917408e46cebe622008ac86a7ce40507c603', 'removed_ids': [{'old_id': 'до-тестування', 'new_id': 'before-testing', 'binding': 'Before testing', 'line': 10}, {'old_id': 'окремі-зобовязання', 'new_id': 'separate-obligations', 'binding': 'Separate obligations', 'line': 18}, {'old_id': 'умовні-сценарії', 'new_id': 'conditional-scenarios', 'binding': 'Conditional scenarios', 'line': 34}, {'old_id': 'виконання-та-завершення', 'new_id': 'execution-and-completion', 'binding': 'Execution and completion', 'line': 40}], 'changed_targets': [{'old_target': 'references/testing-rules.md#scoped-перевірки-та-завершення', 'new_target': 'references/testing-rules.md#scoped-checks-and-completion', 'count': 1, 'line': 38}, {'old_target': 'references/testing-rules.md#scoped-перевірки-та-завершення', 'new_target': 'references/testing-rules.md#scoped-checks-and-completion', 'count': 1, 'line': 50}], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 503, 'end': 503, 'before': '<a id="до-тестування"></a>\n', 'after': ''}, {'start': 1445, 'end': 1445, 'before': '<a id="окремі-зобовязання"></a>\n', 'after': ''}, {'start': 3296, 'end': 3296, 'before': '<a id="умовні-сценарії"></a>\n', 'after': ''}, {'start': 3434, 'end': 3455, 'before': 'перевірки-та-завершення', 'after': 'checks-and-completion'}, {'start': 3721, 'end': 3721, 'before': '<a id="виконання-та-завершення"></a>\n', 'after': ''}, {'start': 5431, 'end': 5452, 'before': 'перевірки-та-завершення', 'after': 'checks-and-completion'}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="до-тестування"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="окремі-зобовязання"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="умовні-сценарії"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="виконання-та-завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': 'references/testing-rules.md#scoped-перевірки-та-завершення', 'reason': 'Exact original cross-file link target and heading fragment; target compatibility anchor is retained.'}}], 'pre_literals_sha256': '4274eac1f876641aff552991e154cffbd3e8c27e9cc6d2ffac3727d056243e48', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'skills/entity-e2e-coverage/references/matrix.md': {'path': 'skills/entity-e2e-coverage/references/matrix.md', 'pre_anchor_sha256': '94348a1ac21e84fad82d8e404dd99799fe959f05af9bed61815f554d87feaedb', 'current_sha256': '7a19b54979c16106bb75b78ce99e76c5370840524bdfdc0a35ad1a23da6cc116', 'removed_ids': [{'old_id': 'матриця-й-перевірка-звіту', 'new_id': 'matrix-and-report-validation', 'binding': 'Matrix and report validation', 'line': 1}, {'old_id': 'формат', 'new_id': 'format', 'binding': 'Format', 'line': 7}, {'old_id': 'реалістичний-приклад', 'new_id': 'realistic-example', 'binding': 'Realistic example', 'line': 30}, {'old_id': 'умовні-поля-для-filters--keyboard--visual', 'new_id': 'conditional-fields-for-filters--keyboard--visual', 'binding': 'Conditional fields for filters / keyboard / visual', 'line': 40}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="матриця-й-перевірка-звіту"></a>\n', 'after': ''}, {'start': 365, 'end': 365, 'before': '<a id="формат"></a>\n', 'after': ''}, {'start': 2872, 'end': 2872, 'before': '<a id="реалістичний-приклад"></a>\n', 'after': ''}, {'start': 4070, 'end': 4070, 'before': '<a id="умовні-поля-для-filters--keyboard--visual"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="матриця-й-перевірка-звіту"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="формат"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="реалістичний-приклад"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="умовні-поля-для-filters--keyboard--visual"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': '4ddabbfc8bf00e95a5840de5b001e68f5d99eb758d8acf668523610da9d557b7', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'skills/entity-e2e-coverage/references/testing-rules.md': {'path': 'skills/entity-e2e-coverage/references/testing-rules.md', 'pre_anchor_sha256': 'b3005971178abeb238edcd9c56b275f586ca05b2894a9c4f610667a30d7762c0', 'current_sha256': 'aa6308ff8dd05b912c4f76c8a5c7fe0ff94ad30a5b1d028ce5dfe6b081d4468a', 'removed_ids': [{'old_id': 'правила-тестування-сутностей', 'new_id': 'entity-testing-rules', 'binding': 'Entity testing rules', 'line': 1}, {'old_id': 'загальні-інваріанти-цього-скілу', 'new_id': 'general-invariants-of-this-skill', 'binding': 'General invariants of this skill', 'line': 7}, {'old_id': 'scoped-перевірки-та-завершення', 'new_id': 'scoped-checks-and-completion', 'binding': 'Scoped checks and completion', 'line': 20}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="правила-тестування-сутностей"></a>\n', 'after': ''}, {'start': 400, 'end': 400, 'before': '<a id="загальні-інваріанти-цього-скілу"></a>\n', 'after': ''}, {'start': 3778, 'end': 3778, 'before': '<a id="scoped-перевірки-та-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="правила-тестування-сутностей"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="загальні-інваріанти-цього-скілу"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="scoped-перевірки-та-завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'c3745251177da435f6a5e676dbf01d883b2b509900361479120ff5afc88c3df7', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'skills/interface-review/SKILL.md': {'path': 'skills/interface-review/SKILL.md', 'pre_anchor_sha256': '40bee6d91d5721738737b68ec8e4638c8ba339783ba2caef4984f681f7f9c77e', 'current_sha256': 'a15f85159093600fd6151e924fb605666b8c24e962c9f81b93011ef632180ec4', 'removed_ids': [{'old_id': 'interface-review--оркестратор-повного-ревю-інтерфейсу', 'new_id': 'interface-review--complete-interface-review-orchestrator', 'binding': 'interface-review — complete interface review orchestrator', 'line': 6}, {'old_id': 'коли-застосовувати', 'new_id': 'when-to-use', 'binding': 'When to use', 'line': 15}, {'old_id': 'порядок', 'new_id': 'sequence', 'binding': 'Sequence', 'line': 22}, {'old_id': 'звіт-і-гейт', 'new_id': 'report-and-gate', 'binding': 'Report and gate', 'line': 54}, {'old_id': 'режим-дифу--pr', 'new_id': 'diff--pr-mode', 'binding': 'Diff / PR mode', 'line': 62}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 758, 'end': 758, 'before': '<a id="interface-review--оркестратор-повного-ревю-інтерфейсу"></a>\n', 'after': ''}, {'start': 1247, 'end': 1247, 'before': '<a id="коли-застосовувати"></a>\n', 'after': ''}, {'start': 1475, 'end': 1475, 'before': '<a id="порядок"></a>\n', 'after': ''}, {'start': 3818, 'end': 3818, 'before': '<a id="звіт-і-гейт"></a>\n', 'after': ''}, {'start': 4165, 'end': 4165, 'before': '<a id="режим-дифу--pr"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="interface-review--оркестратор-повного-ревю-інтерфейсу"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="коли-застосовувати"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="порядок"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="звіт-і-гейт"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="режим-дифу--pr"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'aae0b23c5d640e9e512265a10b1f142defa5788e28545744642c9cb31f635467', 'current_literals_sha256': '1bf6cfd73b37d3d74726cd0682d6b1d2698ac4355dea4efdd343609c1841839c'},
    'skills/pattern-architecture-review/SKILL.md': {'path': 'skills/pattern-architecture-review/SKILL.md', 'pre_anchor_sha256': '00737ab24eb9e121b44083cbd3009ba92da6ee3f0cbfc10b43d8d2e0429287d2', 'current_sha256': '010dd2712ea5040bc11f7b756a2f465aa810eeb56816fe9edaa4ee56f587fa56', 'removed_ids': [{'old_id': '1-визнач-межі-й-контекст', 'new_id': '1-establish-boundaries-and-context', 'binding': '1. Establish boundaries and context', 'line': 10}, {'old_id': '2-знайди-реальну-причину-для-зміни', 'new_id': '2-find-a-real-reason-to-change', 'binding': '2. Find a real reason to change', 'line': 21}, {'old_id': '3-оціни-відповідні-шаблони-gof', 'new_id': '3-assess-appropriate-gof-patterns', 'binding': '3. Assess appropriate GoF patterns', 'line': 38}, {'old_id': 'оцінка-придатності', 'new_id': 'fit-assessment', 'binding': 'Fit assessment', 'line': 44}, {'old_id': '4-застосуй-окрему-лінзу-kiss-dry-і-solid', 'new_id': '4-apply-a-separate-kiss-dry-and-solid-lens', 'binding': '4. Apply a separate KISS, DRY and SOLID lens', 'line': 69}, {'old_id': '5-перевір-clean-code-та-clean-architecture-окремо', 'new_id': '5-check-clean-code-and-clean-architecture-separately', 'binding': '5. Check Clean Code and Clean Architecture separately', 'line': 87}, {'old_id': '6-видай-короткий-звіт', 'new_id': '6-deliver-a-concise-report', 'binding': '6. Deliver a concise report', 'line': 116}, {'old_id': 'знахідка-коротка-назва', 'new_id': 'finding', 'binding': 'Finding: <short name>', 'line': 122, 'mapping_correction': 'Independent plan critique: native verifier strips inline HTML then surrounding whitespace; Finding: <short name> maps to finding. No incoming reference uses this ID.'}, {'old_id': 'межі-й-повязані-скіли', 'new_id': 'boundaries-and-related-skills', 'binding': 'Boundaries and related skills', 'line': 135}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 748, 'end': 748, 'before': '<a id="1-визнач-межі-й-контекст"></a>\n', 'after': ''}, {'start': 1417, 'end': 1417, 'before': '<a id="2-знайди-реальну-причину-для-зміни"></a>\n', 'after': ''}, {'start': 2214, 'end': 2214, 'before': '<a id="3-оціни-відповідні-шаблони-gof"></a>\n', 'after': ''}, {'start': 2534, 'end': 2534, 'before': '<a id="оцінка-придатності"></a>\n', 'after': ''}, {'start': 4496, 'end': 4496, 'before': '<a id="4-застосуй-окрему-лінзу-kiss-dry-і-solid"></a>\n', 'after': ''}, {'start': 6251, 'end': 6251, 'before': '<a id="5-перевір-clean-code-та-clean-architecture-окремо"></a>\n', 'after': ''}, {'start': 7618, 'end': 7618, 'before': '<a id="6-видай-короткий-звіт"></a>\n', 'after': ''}, {'start': 7734, 'end': 7734, 'before': '<a id="знахідка-коротка-назва"></a>\n', 'after': ''}, {'start': 8558, 'end': 8558, 'before': '<a id="межі-й-повязані-скіли"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="1-визнач-межі-й-контекст"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="2-знайди-реальну-причину-для-зміни"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="3-оціни-відповідні-шаблони-gof"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="оцінка-придатності"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="4-застосуй-окрему-лінзу-kiss-dry-і-solid"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="5-перевір-clean-code-та-clean-architecture-окремо"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="6-видай-короткий-звіт"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 7, 'record': {'text': '<a id="знахідка-коротка-назва"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 8, 'record': {'text': '<a id="межі-й-повязані-скіли"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'a5b936a2fa83e2cdc7a8aab3734c9a0ebb85f34092a8f78435feb2ed8d108028', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
    'skills/plan/acceptance-spec/SKILL.md': {'path': 'skills/plan/acceptance-spec/SKILL.md', 'pre_anchor_sha256': 'c7fc1efcebd856f3a5cc9e0c1717b8f1cf82ea1de3a1e88de62c1658da84a64b', 'current_sha256': 'ca50e57454b1ebd51b8987591de6b40dc5ed18770af5ba4d10eef556e30424aa', 'removed_ids': [{'old_id': 'acceptance-spec--фіча-як-спостережувана-поведінка', 'new_id': 'acceptance-spec--a-feature-as-observable-behavior', 'binding': 'acceptance-spec — a feature as observable behavior', 'line': 6}, {'old_id': '1-збери-сценарії', 'new_id': '1-collect-scenarios', 'binding': '1. Collect scenarios', 'line': 18}, {'old_id': '2-заповни-таблицю', 'new_id': '2-fill-in-the-table', 'binding': '2. Fill in the table', 'line': 31}, {'old_id': '3-привяжи-до-роботи', 'new_id': '3-connect-it-to-the-work', 'binding': '3. Connect it to the work', 'line': 48}, {'old_id': '4-завершення', 'new_id': '4-completion', 'binding': '4. Completion', 'line': 57}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 394, 'end': 394, 'before': '<a id="acceptance-spec--фіча-як-спостережувана-поведінка"></a>\n', 'after': ''}, {'start': 880, 'end': 880, 'before': '<a id="1-збери-сценарії"></a>\n', 'after': ''}, {'start': 1433, 'end': 1433, 'before': '<a id="2-заповни-таблицю"></a>\n', 'after': ''}, {'start': 2257, 'end': 2257, 'before': '<a id="3-привяжи-до-роботи"></a>\n', 'after': ''}, {'start': 2577, 'end': 2577, 'before': '<a id="4-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="acceptance-spec--фіча-як-спостережувана-поведінка"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="1-збери-сценарії"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="2-заповни-таблицю"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="3-привяжи-до-роботи"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="4-завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'bef642ce94174d2eca6990bdf595180a1c131324930e0037a41569a2d28854c5', 'current_literals_sha256': 'e350bfe2beef0ec55c6448e039ccd77c4268f65fd7f2eff8d3d928ede65120a0'},
    'skills/plan/cto-agenda/SKILL.md': {'path': 'skills/plan/cto-agenda/SKILL.md', 'pre_anchor_sha256': 'e2046c8539ba0e6de8676a4946c2d95c95d9a723ee8bfe84c4ad4cdc3dc192c5', 'current_sha256': 'e6272cb4a21d118d05541a1d55dab619b787d3e279bd70b6cd31f641da323e40', 'removed_ids': [{'old_id': 'cto-agenda--що-робити-далі', 'new_id': 'cto-agenda--what-to-do-next', 'binding': 'cto-agenda — what to do next', 'line': 6}, {'old_id': '1-опертись-на-брифінг', 'new_id': '1-start-from-the-briefing', 'binding': '1. Start from the briefing', 'line': 17}, {'old_id': '2-зібрати-кандидатів-із-перелічених-джерел', 'new_id': '2-collect-candidates-from-the-listed-sources', 'binding': '2. Collect candidates from the listed sources', 'line': 25}, {'old_id': '3-розкласти-по-двох-осях', 'new_id': '3-classify-on-two-axes', 'binding': '3. Classify on two axes', 'line': 49}, {'old_id': '4-відокремити-рішення-людини', 'new_id': '4-separate-human-decisions', 'binding': '4. Separate human decisions', 'line': 62}, {'old_id': '5-назвати-хід', 'new_id': '5-name-the-move', 'binding': '5. Name the move', 'line': 71}, {'old_id': '6-дім-агенди', 'new_id': '6-where-the-agenda-lives', 'binding': '6. Where the agenda lives', 'line': 81}, {'old_id': '7-завершення', 'new_id': '7-completion', 'binding': '7. Completion', 'line': 89}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 426, 'end': 426, 'before': '<a id="cto-agenda--що-робити-далі"></a>\n', 'after': ''}, {'start': 872, 'end': 872, 'before': '<a id="1-опертись-на-брифінг"></a>\n', 'after': ''}, {'start': 1179, 'end': 1179, 'before': '<a id="2-зібрати-кандидатів-із-перелічених-джерел"></a>\n', 'after': ''}, {'start': 2539, 'end': 2539, 'before': '<a id="3-розкласти-по-двох-осях"></a>\n', 'after': ''}, {'start': 3093, 'end': 3093, 'before': '<a id="4-відокремити-рішення-людини"></a>\n', 'after': ''}, {'start': 3367, 'end': 3367, 'before': '<a id="5-назвати-хід"></a>\n', 'after': ''}, {'start': 3739, 'end': 3739, 'before': '<a id="6-дім-агенди"></a>\n', 'after': ''}, {'start': 4057, 'end': 4057, 'before': '<a id="7-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="cto-agenda--що-робити-далі"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="1-опертись-на-брифінг"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="2-зібрати-кандидатів-із-перелічених-джерел"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="3-розкласти-по-двох-осях"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="4-відокремити-рішення-людини"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="5-назвати-хід"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="6-дім-агенди"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 7, 'record': {'text': '<a id="7-завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': '7be949da2d0d3dd120b58142ecf3e0204eef927d9bc742f4c215af034dcfa535', 'current_literals_sha256': 'bec8311517acb484421ec6b912ca984e0bf29d499b54fa886c7fbefe4891552f'},
    'skills/plan/cto-research/SKILL.md': {'path': 'skills/plan/cto-research/SKILL.md', 'pre_anchor_sha256': 'ef24e940adbaf13802902599f88f16ee00b9af2e4a474b65ac5d085bbc4f1623', 'current_sha256': '68d2b981b06afce7134128dcc5a5f7903409ee55e7a68f0350928923492881e5', 'removed_ids': [{'old_id': 'cto-research--брифінг-перед-імплементацією', 'new_id': 'cto-research--the-pre-implementation-briefing', 'binding': 'cto-research — the pre-implementation briefing', 'line': 6}, {'old_id': '1-знайди-дім-брифінгу', 'new_id': '1-find-the-briefings-home', 'binding': "1. Find the briefing's home", 'line': 16}, {'old_id': '2-гейт-свіжості-перший-крок-коли-файл-уже-є', 'new_id': '2-freshness-gate-the-first-step-when-the-file-exists', 'binding': '2. Freshness gate (the first step when the file exists)', 'line': 25}, {'old_id': '3-збери-по-пяти-осях', 'new_id': '3-research-five-axes', 'binding': '3. Research five axes', 'line': 41}, {'old_id': '4-напиши-брифінг', 'new_id': '4-write-the-briefing', 'binding': '4. Write the briefing', 'line': 58}, {'old_id': '5-завершення', 'new_id': '5-completion', 'binding': '5. Completion', 'line': 77}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 454, 'end': 454, 'before': '<a id="cto-research--брифінг-перед-імплементацією"></a>\n', 'after': ''}, {'start': 847, 'end': 847, 'before': '<a id="1-знайди-дім-брифінгу"></a>\n', 'after': ''}, {'start': 1502, 'end': 1502, 'before': '<a id="2-гейт-свіжості-перший-крок-коли-файл-уже-є"></a>\n', 'after': ''}, {'start': 2767, 'end': 2767, 'before': '<a id="3-збери-по-пяти-осях"></a>\n', 'after': ''}, {'start': 3709, 'end': 3709, 'before': '<a id="4-напиши-брифінг"></a>\n', 'after': ''}, {'start': 4550, 'end': 4550, 'before': '<a id="5-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="cto-research--брифінг-перед-імплементацією"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="1-знайди-дім-брифінгу"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="2-гейт-свіжості-перший-крок-коли-файл-уже-є"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="3-збери-по-пяти-осях"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="4-напиши-брифінг"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="5-завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'b89d10b52639b6bca90b1890b8516fe8d23df2418c2dae12c4e40e4b3e56e6f2', 'current_literals_sha256': '6c27c3c706502eac4820fae8fe10e33018ad0e8f2c3c8836474e063bd14f5a32'},
    'skills/plan/plan-critique/SKILL.md': {'path': 'skills/plan/plan-critique/SKILL.md', 'pre_anchor_sha256': 'ea347435529f790bce6e134e4242aa7a46abf22f60982e37af02379406465ad2', 'current_sha256': 'e8323990106a6387c7478016ebf6f3b1efb406bdd862c8e2fdfeb3b12db6ce28', 'removed_ids': [{'old_id': 'plan-critique--чотири-лінзи-по-плану', 'new_id': 'plan-critique--four-lenses-on-a-plan', 'binding': 'plan-critique — four lenses on a plan', 'line': 6}, {'old_id': '1-підготуй-матеріал', 'new_id': '1-prepare-the-material', 'binding': '1. Prepare the material', 'line': 17}, {'old_id': '2-прожени-чотири-лінзи-паралельно', 'new_id': '2-run-four-lenses-in-parallel', 'binding': '2. Run four lenses in parallel', 'line': 24}, {'old_id': 'лінза-що-не-повернулась', 'new_id': 'a-lens-that-did-not-return', 'binding': 'A lens that did not return', 'line': 52}, {'old_id': '3-зведи', 'new_id': '3-consolidate', 'binding': '3. Consolidate', 'line': 67}, {'old_id': '4-завершення', 'new_id': '4-completion', 'binding': '4. Completion', 'line': 76}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 420, 'end': 420, 'before': '<a id="plan-critique--чотири-лінзи-по-плану"></a>\n', 'after': ''}, {'start': 861, 'end': 861, 'before': '<a id="1-підготуй-матеріал"></a>\n', 'after': ''}, {'start': 1096, 'end': 1096, 'before': '<a id="2-прожени-чотири-лінзи-паралельно"></a>\n', 'after': ''}, {'start': 2469, 'end': 2469, 'before': '<a id="лінза-що-не-повернулась"></a>\n', 'after': ''}, {'start': 3158, 'end': 3158, 'before': '<a id="3-зведи"></a>\n', 'after': ''}, {'start': 3438, 'end': 3438, 'before': '<a id="4-завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="plan-critique--чотири-лінзи-по-плану"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="1-підготуй-матеріал"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="2-прожени-чотири-лінзи-паралельно"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="лінза-що-не-повернулась"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="3-зведи"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="4-завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': '55223c081ea415de05196f5f01fda6a0edf209abf572ba2424169327c83b7bab', 'current_literals_sha256': 'e7f5ec43813b66a81317877916ca3e677b5be449df8a732100eacadcabce0b3b'},
    'skills/plan/plan-defense/SKILL.md': {'path': 'skills/plan/plan-defense/SKILL.md', 'pre_anchor_sha256': 'a4f7b9a55a873047db2cc57298080e1b63e70fc26d4ed862f1d0cd2a7c2af9f3', 'current_sha256': 'bbfd8dac25c17be31d6277c447e007aae09a3077da2a2818ecbce81a8995d141', 'removed_ids': [{'old_id': 'plan-defense--пять-питань-на-які-план-відповідає-рядком', 'new_id': 'plan-defense--five-questions-answered-by-a-line-in-the-plan', 'binding': 'plan-defense — five questions answered by a line in the plan', 'line': 6}, {'old_id': 'питання', 'new_id': 'questions', 'binding': 'Questions', 'line': 16}, {'old_id': 'форма-відповіді', 'new_id': 'answer-format', 'binding': 'Answer format', 'line': 33}, {'old_id': 'завершення', 'new_id': 'completion', 'binding': 'Completion', 'line': 50}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 439, 'end': 439, 'before': '<a id="plan-defense--пять-питань-на-які-план-відповідає-рядком"></a>\n', 'after': ''}, {'start': 866, 'end': 866, 'before': '<a id="питання"></a>\n', 'after': ''}, {'start': 1897, 'end': 1897, 'before': '<a id="форма-відповіді"></a>\n', 'after': ''}, {'start': 2369, 'end': 2369, 'before': '<a id="завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="plan-defense--пять-питань-на-які-план-відповідає-рядком"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="питання"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="форма-відповіді"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'cd0c9656a7424d670fb9e86e5dce9ec52eecbe1a46c5684a6795f4c372e1521d', 'current_literals_sha256': '0b1fd5100e65ce0a173ba8e8f8c8f2d9cad0d8a00fafe77fa52a6bd9685f52b8'},
    'skills/ship/post-deploy-check/SKILL.md': {'path': 'skills/ship/post-deploy-check/SKILL.md', 'pre_anchor_sha256': '1dc7192777bc13ed2cfe2bb26f2d694175a251079f34083881c13bb3e224c677', 'current_sha256': '50b0ecd2821588fe9a8cdd6159ce5fab56f0721dc14bc8b092fea25528de53af', 'removed_ids': [{'old_id': 'post-deploy-check--фіча-на-проді-а-не-в-тесті', 'new_id': 'post-deploy-check--the-feature-in-production-not-in-a-test', 'binding': 'post-deploy-check — the feature in production, not in a test', 'line': 6}, {'old_id': '1-знайди-звіт-фічі', 'new_id': '1-find-the-feature-report', 'binding': '1. Find the feature report', 'line': 17}, {'old_id': '2-зясуй-що-взагалі-доступно', 'new_id': '2-establish-what-is-actually-accessible', 'binding': '2. Establish what is actually accessible', 'line': 27}, {'old_id': '3-перепройди-ключові-сценарії', 'new_id': '3-re-run-key-scenarios', 'binding': '3. Re-run key scenarios', 'line': 42}, {'old_id': '4-дивись-чого-в-тесті-не-буває', 'new_id': '4-inspect-what-tests-do-not-show', 'binding': '4. Inspect what tests do not show', 'line': 54}, {'old_id': '5-допиши-в-звіт', 'new_id': '5-append-to-the-report', 'binding': '5. Append to the report', 'line': 63}, {'old_id': 'завершення', 'new_id': 'completion', 'binding': 'Completion', 'line': 78}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 352, 'end': 352, 'before': '<a id="post-deploy-check--фіча-на-проді-а-не-в-тесті"></a>\n', 'after': ''}, {'start': 783, 'end': 783, 'before': '<a id="1-знайди-звіт-фічі"></a>\n', 'after': ''}, {'start': 1147, 'end': 1147, 'before': '<a id="2-зясуй-що-взагалі-доступно"></a>\n', 'after': ''}, {'start': 1826, 'end': 1826, 'before': '<a id="3-перепройди-ключові-сценарії"></a>\n', 'after': ''}, {'start': 2326, 'end': 2326, 'before': '<a id="4-дивись-чого-в-тесті-не-буває"></a>\n', 'after': ''}, {'start': 2692, 'end': 2692, 'before': '<a id="5-допиши-в-звіт"></a>\n', 'after': ''}, {'start': 3202, 'end': 3202, 'before': '<a id="завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="post-deploy-check--фіча-на-проді-а-не-в-тесті"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="1-знайди-звіт-фічі"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="2-зясуй-що-взагалі-доступно"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="3-перепройди-ключові-сценарії"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="4-дивись-чого-в-тесті-не-буває"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="5-допиши-в-звіт"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'fbfdd0f2a3e5a8b720173ff41732d65ec99c5bb5e7b93a49d29e67590b447c38', 'current_literals_sha256': '7c1538ff6f124671897ead4e331975cbdee43669acbf81e088692cedae9721d9'},
    'skills/ship/ship-report/SKILL.md': {'path': 'skills/ship/ship-report/SKILL.md', 'pre_anchor_sha256': '9c5606305aebbd398d56a753a5c53965b321f2b01c7b2b41bab12fe830fcc9f8', 'current_sha256': 'f47f749aa9b24fee8546bfd811c3246b781dc385db6c2a468b544d88621fd61d', 'removed_ids': [{'old_id': 'ship-report--звіт-який-читають-замість-диффа', 'new_id': 'ship-report--the-report-people-read-instead-of-the-diff', 'binding': 'ship-report — the report people read instead of the diff', 'line': 6}, {'old_id': 'дім', 'new_id': 'home', 'binding': 'Home', 'line': 16}, {'old_id': 'шість-секцій', 'new_id': 'six-sections', 'binding': 'Six sections', 'line': 26}, {'old_id': '1-що-зроблено', 'new_id': '1-what-was-done', 'binding': '1. What was done', 'line': 33}, {'old_id': '2-протестовані-сценарії', 'new_id': '2-tested-scenarios', 'binding': '2. Tested scenarios', 'line': 40}, {'old_id': '3-неочевидне', 'new_id': '3-non-obvious-findings', 'binding': '3. Non-obvious findings', 'line': 53}, {'old_id': '4-скріни', 'new_id': '4-screenshots', 'binding': '4. Screenshots', 'line': 64}, {'old_id': '5-проходка-по-user-flow', 'new_id': '5-user-flow-walkthrough', 'binding': '5. User-flow walkthrough', 'line': 71}, {'old_id': '6-ризики-й-обмеження', 'new_id': '6-risks-and-limitations', 'binding': '6. Risks and limitations', 'line': 80}, {'old_id': 'завершення', 'new_id': 'completion', 'binding': 'Completion', 'line': 87}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 453, 'end': 453, 'before': '<a id="ship-report--звіт-який-читають-замість-диффа"></a>\n', 'after': ''}, {'start': 889, 'end': 889, 'before': '<a id="дім"></a>\n', 'after': ''}, {'start': 1337, 'end': 1337, 'before': '<a id="шість-секцій"></a>\n', 'after': ''}, {'start': 1546, 'end': 1546, 'before': '<a id="1-що-зроблено"></a>\n', 'after': ''}, {'start': 1738, 'end': 1738, 'before': '<a id="2-протестовані-сценарії"></a>\n', 'after': ''}, {'start': 2315, 'end': 2315, 'before': '<a id="3-неочевидне"></a>\n', 'after': ''}, {'start': 2718, 'end': 2718, 'before': '<a id="4-скріни"></a>\n', 'after': ''}, {'start': 2887, 'end': 2887, 'before': '<a id="5-проходка-по-user-flow"></a>\n', 'after': ''}, {'start': 3156, 'end': 3156, 'before': '<a id="6-ризики-й-обмеження"></a>\n', 'after': ''}, {'start': 3363, 'end': 3363, 'before': '<a id="завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="ship-report--звіт-який-читають-замість-диффа"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="дім"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="шість-секцій"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="1-що-зроблено"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="2-протестовані-сценарії"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="3-неочевидне"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="4-скріни"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 7, 'record': {'text': '<a id="5-проходка-по-user-flow"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 8, 'record': {'text': '<a id="6-ризики-й-обмеження"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 9, 'record': {'text': '<a id="завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': '77b8a5d5dfcbaad9b49dd322db1ba77ff1b586491622dea086a2214cba79911d', 'current_literals_sha256': '4340ac518ef1b6e839b8b3074217c67d8ed45ca431bce9fb978883e0647d9a17'},
    'skills/utils/repo-bootstrap/SKILL.md': {'path': 'skills/utils/repo-bootstrap/SKILL.md', 'pre_anchor_sha256': '635aa7d84eeaee8541dafbf158d4f1612a7b9ba3511f5128a72d045a564d5d9b', 'current_sha256': '1349eab9a25cd9db9859390330f6f4cbe544f8e09ff1456ef098abfeef9fb78b', 'removed_ids': [{'old_id': 'repo-bootstrap--інвентар-того-що-репо-має-мати', 'new_id': 'repo-bootstrap--inventory-of-what-a-repository-needs', 'binding': 'repo-bootstrap — inventory of what a repository needs', 'line': 6}, {'old_id': 'головне-правило-не-вигадувати-вміст', 'new_id': 'main-rule-do-not-invent-content', 'binding': 'Main rule: do not invent content', 'line': 19}, {'old_id': 'дві-гілки', 'new_id': 'two-modes', 'binding': 'Two modes', 'line': 35}, {'old_id': 'інвентар', 'new_id': 'inventory', 'binding': 'Inventory', 'line': 48}, {'old_id': 'порядок', 'new_id': 'sequence', 'binding': 'Sequence', 'line': 73}, {'old_id': 'завершення', 'new_id': 'completion', 'binding': 'Completion', 'line': 88}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 490, 'end': 490, 'before': '<a id="repo-bootstrap--інвентар-того-що-репо-має-мати"></a>\n', 'after': ''}, {'start': 1441, 'end': 1441, 'before': '<a id="головне-правило-не-вигадувати-вміст"></a>\n', 'after': ''}, {'start': 2228, 'end': 2228, 'before': '<a id="дві-гілки"></a>\n', 'after': ''}, {'start': 3143, 'end': 3143, 'before': '<a id="інвентар"></a>\n', 'after': ''}, {'start': 5288, 'end': 5288, 'before': '<a id="порядок"></a>\n', 'after': ''}, {'start': 6553, 'end': 6553, 'before': '<a id="завершення"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="repo-bootstrap--інвентар-того-що-репо-має-мати"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="головне-правило-не-вигадувати-вміст"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="дві-гілки"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="інвентар"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="порядок"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="завершення"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': '09bf0093a9b48c5aae474d9004de3cfe88198c061925e8c307c5f0722fd0a58c', 'current_literals_sha256': 'e07cfd39ee8362b084c22f3d2a4105ec0a947f38d9826f8ee406f2b8f9c22e6b'},
    'skills/ux-review/SKILL.md': {'path': 'skills/ux-review/SKILL.md', 'pre_anchor_sha256': '30b3cac8a3957f249cfbd56e19e6658ab39aeb399c06e46fece3912f40785be6', 'current_sha256': 'ed121a0e57e2ec85a7fbe67201445366e0e51959741d2d61690dd986835a24a6', 'removed_ids': [{'old_id': 'ux-review--аудит-ux-проти-цитованих-правил', 'new_id': 'ux-review--ux-audit-against-cited-rules', 'binding': 'ux-review — UX audit against cited rules', 'line': 6}, {'old_id': 'коли-застосовувати', 'new_id': 'when-to-apply', 'binding': 'When to apply', 'line': 21}, {'old_id': 'порядок', 'new_id': 'procedure', 'binding': 'Procedure', 'line': 29}, {'old_id': 'режим-гейта-pre-flight-готовності', 'new_id': 'gate-mode-readiness-pre-flight', 'binding': 'Gate mode (readiness pre-flight)', 'line': 62}, {'old_id': 'режим-ревю-дифу--pr', 'new_id': 'diff--pr-review-mode', 'binding': 'Diff / PR review mode', 'line': 70}, {'old_id': 'пріоритет-коли-шари-сперечаються', 'new_id': 'priority-when-layers-disagree', 'binding': 'Priority when layers disagree', 'line': 76}, {'old_id': 'чесність', 'new_id': 'honesty', 'binding': 'Honesty', 'line': 87}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 733, 'end': 733, 'before': '<a id="ux-review--аудит-ux-проти-цитованих-правил"></a>\n', 'after': ''}, {'start': 1643, 'end': 1643, 'before': '<a id="коли-застосовувати"></a>\n', 'after': ''}, {'start': 1924, 'end': 1924, 'before': '<a id="порядок"></a>\n', 'after': ''}, {'start': 4612, 'end': 4612, 'before': '<a id="режим-гейта-pre-flight-готовності"></a>\n', 'after': ''}, {'start': 4970, 'end': 4970, 'before': '<a id="режим-ревю-дифу--pr"></a>\n', 'after': ''}, {'start': 5431, 'end': 5431, 'before': '<a id="пріоритет-коли-шари-сперечаються"></a>\n', 'after': ''}, {'start': 6027, 'end': 6027, 'before': '<a id="чесність"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="ux-review--аудит-ux-проти-цитованих-правил"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="коли-застосовувати"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="порядок"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="режим-гейта-pre-flight-готовності"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="режим-ревю-дифу--pr"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="пріоритет-коли-шари-сперечаються"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="чесність"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'bb6b3356fcee67da8e700c0337378b2e14de53366f8dd45088e5bf88ecd6610a', 'current_literals_sha256': '14a0a90c3a573e4289c4d651ed08baade0c9d69befc980b9082c1ee1c6aac77b'},
    'skills/ux-review/references/rules.md': {'path': 'skills/ux-review/references/rules.md', 'pre_anchor_sha256': '6758e9ba854d216bb1d19617daa3bc4012251c55cab253e51f5108a7979b0645', 'current_sha256': 'eddc2da58eabfef0cf65cc5aa5cf6031906c14a27bc8c31d4a6782ac61ebc234', 'removed_ids': [{'old_id': 'ux-review--руллсет-цитовані-ux-правила', 'new_id': 'ux-review--ruleset-cited-ux-rules', 'binding': 'ux-review — ruleset (cited UX rules)', 'line': 1}, {'old_id': '3-wcag-22-ux-дотичні-sc', 'new_id': '3-wcag-22-ux-related-sc', 'binding': '3. WCAG 2.2 (UX-related SC)', 'line': 45}, {'old_id': '4-форми', 'new_id': '4-forms', 'binding': '4. Forms', 'line': 65}, {'old_id': '5-таблиці--списки-даних', 'new_id': '5-tables--data-lists', 'binding': '5. Tables / data lists', 'line': 79}, {'old_id': '6-навігація--ia', 'new_id': '6-navigation--ia', 'binding': '6. Navigation / IA', 'line': 92}, {'old_id': '7-зворотний-звязок-і-стани', 'new_id': '7-feedback-and-states', 'binding': '7. Feedback and states', 'line': 100}, {'old_id': '8-контент--мікрокопі', 'new_id': '8-content--microcopy', 'binding': '8. Content / microcopy', 'line': 110}, {'old_id': '9-мобтачреспонсив', 'new_id': '9-mobiletouchresponsive', 'binding': '9. Mobile/touch/responsive', 'line': 118}, {'old_id': '10-когнітивне-навантаження', 'new_id': '10-cognitive-load', 'binding': '10. Cognitive load', 'line': 126}, {'old_id': '11-стани-інтерактивних-контролів', 'new_id': '11-interactive-control-states', 'binding': '11. Interactive control states', 'line': 134}, {'old_id': 'найавторитетніші-джерела-для-цитування', 'new_id': 'most-authoritative-sources-for-citation', 'binding': 'Most authoritative sources (for citation)', 'line': 144}], 'changed_targets': [], 'banner_changes': [], 'heading_changes': [], 'hunks': [{'start': 0, 'end': 0, 'before': '<a id="ux-review--руллсет-цитовані-ux-правила"></a>\n', 'after': ''}, {'start': 5419, 'end': 5419, 'before': '<a id="3-wcag-22-ux-дотичні-sc"></a>\n', 'after': ''}, {'start': 8856, 'end': 8856, 'before': '<a id="4-форми"></a>\n', 'after': ''}, {'start': 11127, 'end': 11127, 'before': '<a id="5-таблиці--списки-даних"></a>\n', 'after': ''}, {'start': 13018, 'end': 13018, 'before': '<a id="6-навігація--ia"></a>\n', 'after': ''}, {'start': 13861, 'end': 13861, 'before': '<a id="7-зворотний-звязок-і-стани"></a>\n', 'after': ''}, {'start': 15132, 'end': 15132, 'before': '<a id="8-контент--мікрокопі"></a>\n', 'after': ''}, {'start': 15890, 'end': 15890, 'before': '<a id="9-мобтачреспонсив"></a>\n', 'after': ''}, {'start': 16847, 'end': 16847, 'before': '<a id="10-когнітивне-навантаження"></a>\n', 'after': ''}, {'start': 17633, 'end': 17633, 'before': '<a id="11-стани-інтерактивних-контролів"></a>\n', 'after': ''}, {'start': 18755, 'end': 18755, 'before': '<a id="найавторитетніші-джерела-для-цитування"></a>\n', 'after': ''}], 'removed_preserved_literals': [{'index': 0, 'record': {'text': '<a id="ux-review--руллсет-цитовані-ux-правила"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 1, 'record': {'text': '<a id="3-wcag-22-ux-дотичні-sc"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 2, 'record': {'text': '<a id="4-форми"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 3, 'record': {'text': '<a id="5-таблиці--списки-даних"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 4, 'record': {'text': '<a id="6-навігація--ia"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 5, 'record': {'text': '<a id="7-зворотний-звязок-і-стани"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 6, 'record': {'text': '<a id="8-контент--мікрокопі"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 7, 'record': {'text': '<a id="9-мобтачреспонсив"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 8, 'record': {'text': '<a id="10-когнітивне-навантаження"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 9, 'record': {'text': '<a id="11-стани-інтерактивних-контролів"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}, {'index': 10, 'record': {'text': '<a id="найавторитетніші-джерела-для-цитування"></a>', 'reason': 'Exact compatibility anchor preserving the original heading fragment.'}}], 'pre_literals_sha256': 'efcca4fb49fecf8245ab9b40d738b8bd6623a21a0dd575583dc6f9048942611c', 'current_literals_sha256': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'},
}
MAINTAINED_MARKDOWN = ['AGENTS.md',
 'PROVENANCE.md',
 'README.md',
 'adapters/README.md',
 'adapters/legacy-planning/acceptance-spec-portable.md',
 'adapters/legacy-planning/cto-research-portable.md',
 'adapters/legacy-planning/plan-critique-portable.md',
 'adapters/legacy-planning/plan-defense-portable.md',
 'adapters/security/review.md',
 'ai-factory/ai-factory-plan.md',
 'ai-factory/constraint-adoption.md',
 'ai-factory/crg.md',
 'ai-factory/documentation-hygiene.md',
 'ai-factory/feature-lifecycle.md',
 'ai-factory/models.md',
 'ai-factory/onboarding.md',
 'ai-factory/onboarding/change-protocol.md',
 'ai-factory/pre-code-checkpoint.md',
 'ai-factory/review-handoff.md',
 'ai-factory/roadmap.md',
 'ai-factory/status.md',
 'ai-factory/workflow.md',
 'docs/collection.md',
 'docs/guides/ai-assisted-onboarding.md',
 'docs/legacy/ai-factory-plan-entry.md',
 'docs/legacy/session-size.md',
 'docs/migration-0.4.md',
 'docs/onboarding-helper.md',
 'docs/portability-design.md',
 'docs/portable/capabilities.md',
 'docs/portable/change-protocol.md',
 'docs/portable/crg.md',
 'docs/portable/feature-lifecycle.md',
 'docs/portable/models.md',
 'docs/portable/onboarding.md',
 'docs/portable/review-handoff.md',
 'docs/portable/skill-routing.md',
 'docs/portable/workflow.md',
 'docs/session-size-docker.md',
 'docs/session-size.md',
 'docs/translations/en/ai-factory/history.md',
 'docs/translations/en/ai-factory/repo-evidence.md',
 'docs/translations/en/docs/guides/obsidian-cheatsheet.md',
 'docs/translations/en/docs/guides/skills-cheatsheet.md',
 'docs/translations/en/docs/legacy/starter-readme.md',
 'docs/translations/en/rules/agent-stream-to-file.md',
 'docs/translations/en/rules/multi-model-roles.md',
 'docs/translations/en/rules/repo-standards-manifest.md',
 'docs/translations/en/rules/typescript-pocock-idioms.md',
 'evals/lifecycle/README.md',
 'examples/checkpoint/sprint-batch.md',
 'prompts/plan-critic.md',
 'rules/README.md',
 'rules/agent-entry.md',
 'rules/subagent-orchestration-ledger.md',
 'runtime/README.md',
 'runtime/scanners/README.md',
 'skills/anti-slop-design/SKILL.md',
 'skills/arch/caveman/SKILL.md',
 'skills/arch/code-review/SKILL.md',
 'skills/arch/code-review/references/behavior-coverage.md',
 'skills/arch/code-review/references/languages/frameworks/django.md',
 'skills/arch/code-review/references/languages/frameworks/fastapi.md',
 'skills/arch/code-review/references/languages/frameworks/laravel.md',
 'skills/arch/code-review/references/languages/frameworks/react.md',
 'skills/arch/code-review/references/languages/go.md',
 'skills/arch/code-review/references/languages/index.md',
 'skills/arch/code-review/references/languages/php.md',
 'skills/arch/code-review/references/languages/python.md',
 'skills/arch/code-review/references/languages/rust.md',
 'skills/arch/code-review/references/languages/typescript.md',
 'skills/arch/codebase-design/DEEPENING.md',
 'skills/arch/codebase-design/DESIGN-IT-TWICE.md',
 'skills/arch/codebase-design/SKILL.md',
 'skills/arch/diagnosing-bugs/SKILL.md',
 'skills/arch/domain-modeling/ADR-FORMAT.md',
 'skills/arch/domain-modeling/GLOSSARY-FORMAT.md',
 'skills/arch/domain-modeling/SKILL.md',
 'skills/arch/improve-codebase-architecture/HTML-REPORT.md',
 'skills/arch/improve-codebase-architecture/SKILL.md',
 'skills/arch/receiving-code-review/SKILL.md',
 'skills/arch/tdd/SKILL.md',
 'skills/arch/tdd/mocking.md',
 'skills/arch/tdd/tests.md',
 'skills/constraint-driven-development/SKILL.md',
 'skills/constraint-driven-development/references/floor-evidence.md',
 'skills/constraint-driven-development/references/provenance.md',
 'skills/crg/crg-debug-issue/SKILL.md',
 'skills/crg/crg-explore-codebase/SKILL.md',
 'skills/crg/crg-refactor-safely/SKILL.md',
 'skills/crg/crg-review-changes/SKILL.md',
 'skills/deliver/implement-spec/SKILL.md',
 'skills/deliver/implement/SKILL.md',
 'skills/deliver/spec-flow/SKILL.md',
 'skills/deliver/to-spec/SKILL.md',
 'skills/deliver/to-tickets/SKILL.md',
 'skills/deliver/triage/AGENT-BRIEF.md',
 'skills/deliver/triage/OUT-OF-SCOPE.md',
 'skills/deliver/triage/SKILL.md',
 'skills/deliver/wayfinder/SKILL.md',
 'skills/design-pass/SKILL.md',
 'skills/design-pass/references/browser-state-evidence.md',
 'skills/design-pass/references/viewport-coverage.md',
 'skills/entity-e2e-coverage/SKILL.md',
 'skills/entity-e2e-coverage/references/matrix.md',
 'skills/entity-e2e-coverage/references/testing-rules.md',
 'skills/git/git-guardrails-claude-code/SKILL.md',
 'skills/git/pr/CREDITS.md',
 'skills/git/pr/SKILL.md',
 'skills/git/resolving-merge-conflicts/SKILL.md',
 'skills/git/setup-pre-commit/SKILL.md',
 'skills/graphify-local/SKILL.md',
 'skills/interface-review/SKILL.md',
 'skills/pattern-architecture-review/SKILL.md',
 'skills/plan/acceptance-spec/SKILL.md',
 'skills/plan/ask-matt/PHASE-BOUNDARIES.md',
 'skills/plan/ask-matt/SKILL.md',
 'skills/plan/cto-agenda/SKILL.md',
 'skills/plan/cto-research/SKILL.md',
 'skills/plan/grill-me/SKILL.md',
 'skills/plan/grill-with-docs/SKILL.md',
 'skills/plan/grilling/SKILL.md',
 'skills/plan/plan-critique/SKILL.md',
 'skills/plan/plan-defense/SKILL.md',
 'skills/plan/to-questionnaire/SKILL.md',
 'skills/pt/ponytail-audit/SKILL.md',
 'skills/pt/ponytail-debt/SKILL.md',
 'skills/pt/ponytail-gain/SKILL.md',
 'skills/pt/ponytail-help/SKILL.md',
 'skills/pt/ponytail-review/SKILL.md',
 'skills/pt/ponytail/SKILL.md',
 'skills/reference-ui-reconstruction/SKILL.md',
 'skills/ship/frontend-design/SKILL.md',
 'skills/ship/frontend-design/WRITING.md',
 'skills/ship/handoff/SKILL.md',
 'skills/ship/post-deploy-check/SKILL.md',
 'skills/ship/prototype/LOGIC.md',
 'skills/ship/prototype/SKILL.md',
 'skills/ship/prototype/UI.md',
 'skills/ship/research/SKILL.md',
 'skills/ship/retro/SKILL.md',
 'skills/ship/ship-report/SKILL.md',
 'skills/ship/teach/GLOSSARY-FORMAT.md',
 'skills/ship/teach/LEARNING-RECORD-FORMAT.md',
 'skills/ship/teach/MISSION-FORMAT.md',
 'skills/ship/teach/RESOURCES-FORMAT.md',
 'skills/ship/teach/SKILL.md',
 'skills/synced/snapshot-01/canvas-design/SKILL.md',
 'skills/synced/snapshot-01/deep-research/SKILL.md',
 'skills/synced/snapshot-01/deep-research/references/report-writer.md',
 'skills/synced/snapshot-01/deep-research/references/researcher.md',
 'skills/synced/snapshot-01/docs/SKILL.md',
 'skills/synced/snapshot-01/google-workspace/SKILL.md',
 'skills/synced/snapshot-01/google-workspace/references/charts.md',
 'skills/synced/snapshot-01/google-workspace/references/docs.md',
 'skills/synced/snapshot-01/google-workspace/references/sheets.md',
 'skills/synced/snapshot-01/google-workspace/references/slides.md',
 'skills/synced/snapshot-01/import-memory/SKILL.md',
 'skills/synced/snapshot-01/morning/SKILL.md',
 'skills/synced/snapshot-01/skill-creator/SKILL.md',
 'skills/synced/snapshot-01/skill-creator/agents/analyzer.md',
 'skills/synced/snapshot-01/skill-creator/agents/comparator.md',
 'skills/synced/snapshot-01/skill-creator/agents/grader.md',
 'skills/synced/snapshot-01/skill-creator/references/schemas.md',
 'skills/synced/snapshot-02/docs/SKILL.md',
 'skills/synced/snapshot-02/import-memory/SKILL.md',
 'skills/synced/snapshot-02/morning/SKILL.md',
 'skills/synced/snapshot-02/skill-creator/SKILL.md',
 'skills/synced/snapshot-02/skill-creator/agents/analyzer.md',
 'skills/synced/snapshot-02/skill-creator/agents/comparator.md',
 'skills/synced/snapshot-02/skill-creator/agents/grader.md',
 'skills/synced/snapshot-02/skill-creator/references/schemas.md',
 'skills/utils/migrate-to-shoehorn/SKILL.md',
 'skills/utils/repo-bootstrap/SKILL.md',
 'skills/utils/scaffold-exercises/SKILL.md',
 'skills/utils/setup-matt-pocock-skills/SKILL.md',
 'skills/utils/setup-matt-pocock-skills/domain.md',
 'skills/utils/setup-matt-pocock-skills/issue-tracker-github.md',
 'skills/utils/setup-matt-pocock-skills/issue-tracker-gitlab.md',
 'skills/utils/setup-matt-pocock-skills/issue-tracker-local.md',
 'skills/utils/setup-matt-pocock-skills/triage-labels.md',
 'skills/utils/wait-what/SKILL.md',
 'skills/utils/wizard/SKILL.md',
 'skills/utils/writing-for-agents/SKILL-MECHANICS.md',
 'skills/utils/writing-for-agents/SKILL.md',
 'skills/ux-review/SKILL.md',
 'skills/ux-review/references/rules.md',
 'templates/acceptance-full.md',
 'templates/acceptance-portable.md',
 'templates/adapter-full.md',
 'templates/adapter-portable.md']
ANCHOR_EXCLUDED_MARKDOWN = ['ai-factory/history.md',
 'ai-factory/repo-evidence.md',
 'docs/guides/obsidian-cheatsheet.md',
 'docs/guides/skills-cheatsheet.md',
 'docs/legacy/starter-readme.md',
 'rules/agent-stream-to-file.md',
 'rules/multi-model-roles.md',
 'rules/repo-standards-manifest.md',
 'rules/typescript-pocock-idioms.md',
 'work/research/semgrep-ce-paused/README.md',
 'work/research/semgrep-ce-paused/transition/decision-and-proposal.md']


def anchor_migration_active(data):
    return bool(set(ANCHOR_FILES) & set(data))


def restore_anchor(path, raw):
    contract = ANCHOR_FILES[path]
    if digest(raw) != contract['current_sha256']:
        raise ValueError('anchor current bytes mismatch:' + path)
    text = raw.decode()
    for hunk in reversed(contract['hunks']):
        if text[hunk['start']:hunk['end']] != hunk['after']:
            raise ValueError('anchor operation mismatch:' + path)
        text = text[:hunk['start']] + hunk['before'] + text[hunk['end']:]
    restored = text.encode()
    if digest(restored) != contract['pre_anchor_sha256']:
        raise ValueError('anchor pre-source mismatch:' + path)
    return restored


def anchor_content_proof(data):
    restored = dict(data)
    if not anchor_migration_active(data):
        return restored  # Existing synthetic trees have no migration paths.
    for path in ANCHOR_FILES:
        if path not in data:
            raise ValueError('anchor missing mapped file:' + path)
        restored[path] = restore_anchor(path, data[path])
    return restored


def anchor_provenance_proof(data, provenance):
    if not anchor_migration_active(data):
        return {}
    projection = [{k:v for k,v in row.items() if k != 'hunks'} for row in ANCHOR_FILES.values()]
    expected = {'pre_anchor_commit':ANCHOR_COMMIT, 'pre_anchor_manifest_sha256':ANCHOR_MANIFEST,
                'files':projection}
    if provenance.get('anchor_migration') != expected:
        raise ValueError('anchor provenance contract mismatch')
    rows = {r['path']:r for r in provenance['records']}
    reconstructed = {}
    for path, contract in ANCHOR_FILES.items():
        current = rows[path]['preserved_literals']
        if canonical_records_digest(current) != contract['current_literals_sha256']:
            raise ValueError('anchor current literal inventory mismatch:' + path)
        old = list(current)
        previous = -1
        for removed in contract['removed_preserved_literals']:
            index = removed['index']
            if not isinstance(index,int) or index <= previous or not 0 <= index <= len(old):
                raise ValueError('anchor literal removal index mismatch:' + path)
            old.insert(index,removed['record']); previous = index
        if canonical_records_digest(old) != contract['pre_literals_sha256']:
            raise ValueError('anchor original literal inventory mismatch:' + path)
        reconstructed[path] = old
    return reconstructed


def navigation_decode(value):
    # HTML attributes are entity-decoded by HTMLParser; this also checks entities
    # in Markdown targets and rejects malformed/non-UTF8 URL escape sequences.
    value = html.unescape(value)
    if re.search(r'%(?![0-9A-Fa-f]{2})',value):
        raise ValueError('malformed navigation percent escape')
    return unquote(value,encoding='utf-8',errors='strict')


def current_navigation(text):
    """Bounded current-tree parser; unsupported active forms fail closed.

    The reviewed maintained tree has no active reference definitions, HTML hrefs
    or setext headings. Reject those shapes rather than claiming their coverage.
    HTML id/name attributes on any tag are parsed with entity decoding.
    """
    frontmatter = re.match(r'\A---\r?\n.*?\r?\n---(?:\r?\n|$)',text,re.S)
    if frontmatter:
        text = text[frontmatter.end():]
    visible = visible_markdown(text,drop_inline=True)
    raw_visible = without_inline_code(visible_markdown(text),multiline_only=True)
    if re.search(r'^ {0,3}\[[^]\n]+\]:',visible,re.M):
        raise ValueError('unsupported active reference-style navigation')
    lines = raw_visible.splitlines()
    for i,line in enumerate(lines):
        if (i and re.fullmatch(r' {0,3}(?:=+|-{2,})\s*',line) and lines[i-1].strip() and
                not re.match(r'\s*(?:[-*+]|\d+[.)]|#|[|>])(?:\s|$)',lines[i-1])):
            raise ValueError('unsupported active setext heading')
    explicit = []
    class Tags(HTMLParser):
        def handle_starttag(self, tag, attrs):
            seen = set()
            for key,value in attrs:
                if key in ('id','href') or (key == 'name' and tag == 'a'):
                    if key in seen or value is None:
                        raise ValueError('malformed active navigation attribute')
                    seen.add(key)
                    if key == 'href':
                        raise ValueError('unsupported active HTML href navigation')
                    if key == 'id' or (key == 'name' and tag == 'a'):
                        explicit.append(value)
        handle_startendtag = handle_starttag
    parser=Tags(convert_charrefs=True);parser.feed(visible);parser.close()
    # Do not let slug punctuation removal hide entity/percent-encoded Cyrillic
    # in the rendered heading text before checking its generated section ID.
    for line in raw_visible.splitlines():
        heading = re.match(r'^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?$',line)
        if heading and CYRILLIC.search(html.unescape(unquote(heading[1],encoding='utf-8',errors='strict'))):
            raise ValueError('Cyrillic current section ID')
    ids = headings(text) + explicit
    for identifier in ids:
        if CYRILLIC.search(navigation_decode(identifier)):
            raise ValueError('Cyrillic current section ID')
    collisions = [identifier for identifier,count in Counter(ids).items() if count > 1]
    if collisions:
        raise ValueError('current anchor collision')
    return set(ids), markdown_targets(text)


def current_tree_navigation_proof(data):
    if not anchor_migration_active(data):
        return
    found = {n for n in data if n.endswith('.md')}
    expected = set(MAINTAINED_MARKDOWN)
    if found - set(ANCHOR_EXCLUDED_MARKDOWN) != expected:
        raise ValueError('current maintained Markdown inventory mismatch')
    inventory = {n:current_navigation(data[n].decode()) for n in sorted(expected)}
    for path,(ids,targets) in inventory.items():
        for target in targets:
            parsed = urlsplit(html.unescape(target))
            if parsed.scheme or parsed.netloc or not parsed.fragment:
                continue
            fragment = navigation_decode(parsed.fragment)
            if CYRILLIC.search(fragment):
                raise ValueError('Cyrillic current internal fragment:' + path)
            normalized = canonical_target(path, parsed.path)
            # Original external tooling-home references stay outside this package;
            # their immutable bytes are still guarded by the existing proof.
            if normalized.startswith(('../','/')) or parsed.path.startswith('~'):
                continue
            if normalized not in data or not normalized.endswith('.md'):
                raise ValueError('current fragment target file missing:' + path)
            target_ids = inventory[normalized][0] if normalized in inventory else anchors(data[normalized].decode())[0]
            if fragment not in target_ids:
                raise ValueError('current fragment unresolved:' + path)
    for path,contract in ANCHOR_FILES.items():
        actual_ids = inventory[path][0]
        for mapping in contract['removed_ids']:
            if mapping['old_id'] in actual_ids or mapping['new_id'] not in actual_ids:
                raise ValueError('current mapped anchor destination mismatch:' + path)


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
        anchor_restored = anchor_content_proof(data)
        current_tree_navigation_proof(data)
        structural_data = cleanup_content_proof(before, anchor_restored)
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
        restored_literals = anchor_provenance_proof(data, provenance)
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
                    issues.extend(code + ':' + n for code in check_fragments(n, new, structural_data))
                english_coverage(old, new, restored_literals.get(n,row['preserved_literals']))
                if n in restored_literals:
                    english_coverage(old, data[n].decode(), row['preserved_literals'])
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
