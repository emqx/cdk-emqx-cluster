#!/usr/bin/env bash
set -e
session_name=${1-"load-test"}
# window number start with 1, 0 is reserved
window_number=1
n_of_emqx=${2-"1"}
n_of_loadgen=${3-"2"}

function window_run {
    local window=$1
    local cmd=$2
    tmux send-keys -t "$window" "$cmd" Enter;
}

function loadgen_prepare() {
    local lg_host=$1
    local window="$lg_host"
    tmux new-window -a -n $lg_host
    tmux set-option -g allow-rename off
    window_run $window "ssh -o StrictHostKeyChecking=no $lg_host"
    window_run $window "sudo bash"
    window_run $window 'ulimit -n 300000'
    window_run $window "cd /root/emqtt-bench"
    window_run $window 'ipaddrs=$(ip addr |grep -o '192.*/32' | sed 's#/32##g' | paste -s -d , -)'
    tmux rename-window "$lg_host"
}

function emqx_prepare() {
    local emqx_host=$1
    local window=$1
    tmux new-window -a -n "${emqx_host}"
    tmux set-option -g allow-rename off
    window_run "${window}" "ssh -o StrictHostKeyChecking=no ${emqx_host}"
    tmux rename-window "${emqx_host}"
}

# create new_session
tmux new-session -d -s "$session_name"

# create emqx windows
#
for n in $(seq 1 $n_of_emqx);
do
    n=$(($n-1))
    echo "n is $n"
    emqx_prepare "emqx-${n}"
done

# loadgen windows
for n in $(seq 1 $n_of_loadgen);
do
    n=$(($n-1))
    loadgen_prepare "loadgen-${n}"
done
