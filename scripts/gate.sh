#!/bin/sh
# Publication gate: case-insensitive search for internal names, machine paths and credentials over every file,
# verdict JSON included. Prints hits; exits non-zero if there are any. Review each hit by hand.
set -u
cd "$(dirname "$0")/.."
TERMS='pega|blueprint|\bRAP\b|pyze|jpmc|jpmorgan|chase|bny|virtusa|archway|pandia|endava|spark|homeward|sachin|hemanth|jonathan|sid trehan|medhus|victoria|kellerai\.io|/Users/|/Volumes/|keychain|macbook|keller-1|studio|dell|alloy|\bkai\b|kai-|archangel|acceptance engine|beta|resolver|clingo|souffle|contract v0|AWS account|arn:aws'
SECRETS='AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|aws_account|aws_profile|arn:aws|[0-9]{12}:inference-profile|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|-----BEGIN [A-Z ]*PRIVATE KEY|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.'
hits=0
echo "== name and path terms =="
# "Goal Contract v0.2" is the name of Imandra's own Ponens specification (spec/GOAL_CONTRACT_v0_2.md); it is not an internal term.
if grep -rniE "$TERMS" . --exclude-dir=.git --exclude-dir=.tools --exclude-dir=repo --exclude-dir=__pycache__ --exclude=gate.sh | grep -v "Goal Contract v0.2"; then hits=1; fi
echo "== secret-shaped strings and cloud account references =="
if grep -rnE "$SECRETS" . --exclude-dir=.git --exclude-dir=.tools --exclude-dir=repo --exclude-dir=__pycache__ --exclude=gate.sh --exclude=redact.py --exclude=test_cli_plumbing.py --exclude=claude --exclude=bedrock.py; then hits=1; fi
if [ "$hits" = 0 ]; then echo "gate clean"; fi
exit $hits
