// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

export function apply(proposal, proposalId) {
  const proposed_actions = JSON.parse(proposal)["actions"];
  for (const proposed_action of proposed_actions) {
    const definition = actions.get(proposed_action.name);
    definition.apply(proposed_action.args, proposalId);
  }
}
