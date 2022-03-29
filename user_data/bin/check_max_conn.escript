#!/usr/bin/env escript
%%%  Server entry
main(["-s", Port, Parallel]) ->
    process_flag(trap_exit, true),
    NumberOfAcceptors = list_to_integer(Parallel),
    {ok, LPort} = gen_tcp:listen(list_to_integer(Port), [{backlog, NumberOfAcceptors*100}]),
    ok = persistent_term:put(counter, counters:new(3, [write_concurrency])),
    lists:foreach(
      fun(X) ->
              spawn_link(fun() -> acceptor_loop(LPort, X) end)
      end, lists:seq(1, NumberOfAcceptors)),
    main_loop(NumberOfAcceptors);

%%% Client entry
main(["-c", Host, Port0, Parallel]) ->
    main(["-c", Host, Port0, Parallel, ""]);

main(["-c", Host, Port0, Parallel, AddrsStr]) ->
    process_flag(trap_exit, true),
    LocalAddrs0 = lists:map(
                    fun(A) ->
                            {ok, Addr} = inet_parse:address(A),
                            Addr
                    end, string:tokens(AddrsStr, ",")),
    LocalAddrs = case LocalAddrs0 of
                     [] -> [{0,0,0,0}];
                     _ -> LocalAddrs0
                 end,

    NumberOfClients = list_to_integer(Parallel),
    Port = list_to_integer(Port0),
    ok = persistent_term:put(counter, counters:new(3, [write_concurrency])),
    lists:foreach(
      fun(X) ->
              spawn_link(fun() -> run_client(Host, Port, X, LocalAddrs) end)
      end, lists:seq(1, NumberOfClients)),
    main_loop(NumberOfClients);
main(_) ->
    io:format("Check MAX concurrent TCP connections between server/client peers \n\n\n"
              "* Start on Server side: \n"
              "  check_max_conn.escript -s Port ParallelWorkers\n"
              "  e.g.~n"
              "  check_max_conn.escript -s 1883 256 \n"
              "\n"
              "* Start on Client side: rate per worker is 100/s \n"
              "  check_max_conn.escript -c Host Port ParallelWorkers [LocalAddrs]\n"
              "  e.g.~n"
              "  check_max_conn.escript -c lb.int.emqx 1883 10\n"
              "  = for more than 64k conns, multiple local ips is required=~n"
              "  check_max_conn.escript -c lb.int.emqx 1883 10 192.168.1.2,192.168.1.3\n"
             ).

%% Client
run_client(Host, Port, Id, Addrs) ->
    run_client(Host, Port, Id, Addrs, 1).

run_client(Host, Port, Id, Addrs, Offset) when Offset > length(Addrs) ->
    run_client(Host, Port, Id, Addrs, 1);
run_client(Host, Port, Id, Addrs, Offset) ->
    Addr = lists:nth(Offset, Addrs),
    Cnt = persistent_term:get(counter),
    case gen_tcp:connect(Host, Port, [{ip, Addr}]) of
        {ok, _Port} ->
            ok;
        {error, _} = E ->
            io:format("Error ~p to connect with local addr ~p~n", [E, Addr]),
            exit({conn_error, E})
    end,
    ok = counters:add(Cnt, 1, 1),
    receive
        {tcp_closed, _Socket} ->
            ok = counters:add(Cnt, 2, 1);
        {tcp_error, _Socket, _Reason} ->
            ok = counters:add(Cnt, 3, 1)
    after 10 -> %% 100 conns/sec
            ok
    end,
    run_client(Host, Port, Id, Addrs, Offset+1).

%% Server Acceptors
acceptor_loop(LPort, Id) ->
    {ok, _P } = gen_tcp:accept(LPort),
    Cnt = persistent_term:get(counter),
    ok = counters:add(Cnt, 1, 1),
    receive
        {tcp_closed, _Socket} ->
            ok = counters:add(Cnt, 2, 1);
        {tcp_error, _Socket, _Reason} ->
            ok = counters:add(Cnt, 3, 1)
    after 0 ->
            ok
    end,
    acceptor_loop(LPort, Id).

main_loop(0) ->
    print_stats(),
    io:format("All workers are done, exit...~n");
main_loop(N) ->
    receive
        {'EXIT', Pid, Reason} ->
            io:format("Worker is down: ~p ~n", [{Pid, Reason}]),
            main_loop(N-1)
    after 1000 ->
            print_stats(),
            main_loop(N)
    end.

print_stats() ->
    Cnt = persistent_term:get(counter),
    Accepted = counters:get(Cnt, 1),
    Closed = counters:get(Cnt, 2),
    Error = counters:get(Cnt, 3),
    Current = Accepted - Closed,
    Now = erlang:monotonic_time(millisecond),
    Rate = case get(last_accept) of
            undefined -> "N/A";
            {LastAccepted, LastAt} ->
                   (Accepted - LastAccepted) * 1000 / (Now-LastAt)
           end,
    put(last_accept, {Accepted, Now}),
    io:format("Rate: ~p/s,Current: ~p,Accepted:~p,Closed:~p,Error~p~n",
              [Rate, Current, Accepted, Closed, Error]).
