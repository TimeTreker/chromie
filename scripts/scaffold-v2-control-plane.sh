#!/usr/bin/env bash
set -euo pipefail

mkdir -p \
  router/app/prompts \
  agent/app/agents \
  agent/app/prompts \
  agent/app/clients \
  hardware/drivers \
  shared/chromie_contracts \
  orchestrator/clients \
  orchestrator/runtime \
  orchestrator/schemas

create_empty() {
  local file="$1"
  if [ ! -e "$file" ]; then
    : > "$file"
    echo "created $file"
  else
    echo "exists  $file"
  fi
}

files=(
  # Router service
  router/Dockerfile
  router/requirements.txt
  router/README.md
  router/app/__init__.py
  router/app/main.py
  router/app/schema.py
  router/app/rules.py
  router/app/llm_router.py
  router/app/fallback.py
  router/app/prompts/router_system.txt

  # Agent service
  agent/Dockerfile
  agent/requirements.txt
  agent/README.md
  agent/app/__init__.py
  agent/app/main.py
  agent/app/schema.py
  agent/app/runtime.py
  agent/app/dispatcher.py
  agent/app/agents/__init__.py
  agent/app/agents/base.py
  agent/app/agents/conversation.py
  agent/app/agents/speaker.py
  agent/app/agents/robot_pose_controller.py
  agent/app/agents/motion_planner.py
  agent/app/agents/safety.py
  agent/app/agents/tool.py
  agent/app/agents/memory.py
  agent/app/agents/vision.py
  agent/app/prompts/conversation_agent.txt
  agent/app/prompts/speaker_agent.txt
  agent/app/prompts/robot_pose_controller_agent.txt
  agent/app/prompts/motion_planner_agent.txt
  agent/app/prompts/safety_agent.txt
  agent/app/clients/__init__.py
  agent/app/clients/ollama_client.py
  agent/app/clients/tool_client.py
  agent/app/clients/hardware_client.py

  # Host hardware daemon
  hardware/README.md
  hardware/requirements.txt
  hardware/daemon.py
  hardware/schema.py
  hardware/drivers/__init__.py
  hardware/drivers/mock_robot.py
  hardware/drivers/serial_robot.py
  hardware/drivers/servo_controller.py
  hardware/drivers/led_controller.py

  # Shared contracts
  shared/README.md
  shared/chromie_contracts/__init__.py
  shared/chromie_contracts/route.py
  shared/chromie_contracts/agent.py
  shared/chromie_contracts/action.py
  shared/chromie_contracts/session.py
  shared/chromie_contracts/errors.py

  # Orchestrator additions
  orchestrator/clients/__init__.py
  orchestrator/clients/asr_client.py
  orchestrator/clients/tts_client.py
  orchestrator/clients/router_client.py
  orchestrator/clients/agent_client.py
  orchestrator/clients/action_client.py
  orchestrator/runtime/__init__.py
  orchestrator/runtime/session.py
  orchestrator/runtime/interruption.py
  orchestrator/runtime/scheduler.py
  orchestrator/runtime/executor.py
  orchestrator/schemas/__init__.py
  orchestrator/schemas/route.py
  orchestrator/schemas/agent.py
  orchestrator/schemas/action.py
)

for file in "${files[@]}"; do
  create_empty "$file"
done

echo
echo "Scaffold complete."
echo "Review with:"
echo "  tree router agent hardware shared orchestrator/clients orchestrator/runtime orchestrator/schemas"
