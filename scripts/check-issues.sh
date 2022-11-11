#!/usr/bin/env bash
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

todos=$(git grep --line-number -o -E 'TODO\(#[0-9]+\)' -- ':!3rdparty/protobuf')

ex_code=0

repo="microsoft/LSKV"

# check can see the issues on the repo
if ! gh issue list --repo $repo --limit 1 >/dev/null 2>&1; then
    echo "Failed to authenticate with github. Try 'gh auth login'"
    exit 1
fi

# for each todo we found extract the file and the todo text
# the text is in the format 'TODO(#n)' where 'n' is a number.
# We can check the gh issue with that number and ensure it is open.
for todo in $todos; do
    IFS=':' read -ra ADDR <<<"$todo"
    todo_text=${ADDR[2]}

    issue_no=$(echo "$todo_text" | grep -o -e '[[:digit:]]*')

    issue_state=$(gh issue view --repo $repo "$issue_no" --json state --jq '.state' 2>/dev/null)
    if [[ $issue_state != "OPEN" ]]; then
        if [[ $issue_state = "" ]]; then
            issue_state="MISSING"
        fi
        echo "$todo: $issue_state"
        ex_code=1
    fi
done

if [[ $ex_code -eq 0 ]]; then
    echo "All todo issues are open"
else
    echo "Found references to non-open issues"
fi

exit $ex_code
