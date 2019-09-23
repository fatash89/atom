# Julia wrapper for header: atom.h
# Automatically generated using Clang.jl


function atom_get_all_elements_cb(ctx, data_cb, user_data)
    ccall((:atom_get_all_elements_cb, libatom), atom_error_t, (Ptr{redisContext}, Ptr{Cvoid}, Ptr{Cvoid}), ctx, data_cb, user_data)
end

function atom_get_all_data_streams_cb(ctx, element, data_cb, user_data)
    ccall((:atom_get_all_data_streams_cb, libatom), atom_error_t, (Ptr{redisContext}, Cstring, Ptr{Cvoid}, Ptr{Cvoid}), ctx, element, data_cb, user_data)
end

function atom_get_all_elements(ctx, result)
    ccall((:atom_get_all_elements, libatom), atom_error_t, (Ptr{redisContext}, Ptr{Ptr{atom_list_node}}), ctx, result)
end

function atom_get_all_data_streams(ctx, element, result)
    ccall((:atom_get_all_data_streams, libatom), atom_error_t, (Ptr{redisContext}, Cstring, Ptr{Ptr{atom_list_node}}), ctx, element, result)
end

function atom_list_free(list)
    ccall((:atom_list_free, libatom), Cvoid, (Ptr{atom_list_node},), list)
end

function atom_get_response_stream_str(element, buffer)
    ccall((:atom_get_response_stream_str, libatom), Cstring, (Cstring, Ptr{UInt8}), element, buffer)
end

function atom_get_command_stream_str(element, buffer)
    ccall((:atom_get_command_stream_str, libatom), Cstring, (Cstring, Ptr{UInt8}), element, buffer)
end

function atom_get_data_stream_str(element, name, buffer)
    ccall((:atom_get_data_stream_str, libatom), Cstring, (Cstring, Cstring, Ptr{UInt8}), element, name, buffer)
end

function atom_log(ctx, element, level, msg, msg_len)
    ccall((:atom_log, libatom), atom_error_t, (Ptr{redisContext}, Ptr{Element}, Cint, Cstring, Csize_t), ctx, element, level, msg, msg_len)
end
# Julia wrapper for header: element.h
# Automatically generated using Clang.jl


function element_init(ctx, name)
    ccall((:element_init, libatom), Ptr{Element}, (Ptr{redisContext}, Cstring), ctx, name)
end

function element_cleanup(ctx, elem)
    ccall((:element_cleanup, libatom), Cvoid, (Ptr{redisContext}, Ptr{Element}), ctx, elem)
end
# Julia wrapper for header: element_command_send.h
# Automatically generated using Clang.jl


function element_command_send(ctx, elem, cmd_elem, cmd, data, data_len, block, response_cb, user_data, error_str)
    ccall((:element_command_send, libatom), atom_error_t, (Ptr{redisContext}, Ptr{Element}, Cstring, Cstring, Ptr{UInt8}, Csize_t, Bool, Ptr{Cvoid}, Ptr{Cvoid}, Ptr{Cstring}), ctx, elem, cmd_elem, cmd, data, data_len, block, response_cb, user_data, error_str)
end
# Julia wrapper for header: element_command_server.h
# Automatically generated using Clang.jl


function element_command_add(elem, command, cb, cleanup, user_data, timeout)
    ccall((:element_command_add, libatom), Bool, (Ptr{Element}, Cstring, Ptr{Cvoid}, Ptr{Cvoid}, Ptr{Cvoid}, Cint), elem, command, cb, cleanup, user_data, timeout)
end

function element_command_loop(ctx, elem, loop, timeout)
    ccall((:element_command_loop, libatom), atom_error_t, (Ptr{redisContext}, Ptr{Element}, Bool, Cint), ctx, elem, loop, timeout)
end
# Julia wrapper for header: element_entry_read.h
# Automatically generated using Clang.jl


function element_entry_read_loop(ctx, elem, infos, n_infos, loop_forever, timeout)
    ccall((:element_entry_read_loop, libatom), atom_error_t, (Ptr{redisContext}, Ptr{Element}, Ptr{element_entry_read_info}, Csize_t, Bool, Cint), ctx, elem, infos, n_infos, loop_forever, timeout)
end

function element_entry_read_n(ctx, elem, info, n)
    ccall((:element_entry_read_n, libatom), atom_error_t, (Ptr{redisContext}, Ptr{Element}, Ptr{element_entry_read_info}, Csize_t), ctx, elem, info, n)
end

function element_entry_read_since(ctx, elem, info, last_id, timeout, maxcount)
    ccall((:element_entry_read_since, libatom), atom_error_t, (Ptr{redisContext}, Ptr{Element}, Ptr{element_entry_read_info}, Cstring, Cint, Csize_t), ctx, elem, info, last_id, timeout, maxcount)
end
# Julia wrapper for header: element_entry_write.h
# Automatically generated using Clang.jl


function element_entry_write_init(ctx, elem, name, n_keys)
    ccall((:element_entry_write_init, libatom), Ptr{element_entry_write_info}, (Ptr{redisContext}, Ptr{Element}, Cstring, Cint), ctx, elem, name, n_keys)
end

function element_entry_write_cleanup(ctx, stream)
    ccall((:element_entry_write_cleanup, libatom), Cvoid, (Ptr{redisContext}, Ptr{element_entry_write_info}), ctx, stream)
end

function element_entry_write(ctx, stream, timestamp, maxlen)
    ccall((:element_entry_write, libatom), atom_error_t, (Ptr{redisContext}, Ptr{element_entry_write_info}, Cint, Cint), ctx, stream, timestamp, maxlen)
end
# Julia wrapper for header: redis.h
# Automatically generated using Clang.jl


function redis_init_stream_info(ctx, info, name, data_cb, last_id, user_data)
    ccall((:redis_init_stream_info, libatom), Bool, (Ptr{redisContext}, Ptr{redis_stream_info}, Cstring, Ptr{Cvoid}, Cstring, Ptr{Cvoid}), ctx, info, name, data_cb, last_id, user_data)
end

function redis_xread(ctx, infos, n_infos, block, maxcount)
    ccall((:redis_xread, libatom), Bool, (Ptr{redisContext}, Ptr{redis_stream_info}, Cint, Cint, Csize_t), ctx, infos, n_infos, block, maxcount)
end

function redis_xread_parse_kv(reply, items, n_items)
    ccall((:redis_xread_parse_kv, libatom), Bool, (Ptr{redisReply}, Ptr{redis_xread_kv_item}, Csize_t), reply, items, n_items)
end

function redis_xrevrange(ctx, stream_name, data_cb, n, user_data)
    ccall((:redis_xrevrange, libatom), Bool, (Ptr{redisContext}, Cstring, Ptr{Cvoid}, Csize_t, Ptr{Cvoid}), ctx, stream_name, data_cb, n, user_data)
end

function redis_xadd(ctx, stream_name, infos, info_len, maxlen, approx_maxlen, ret_id)
    ccall((:redis_xadd, libatom), Bool, (Ptr{redisContext}, Cstring, Ptr{redis_xadd_info}, Csize_t, Cint, Bool, Ptr{UInt8}), ctx, stream_name, infos, info_len, maxlen, approx_maxlen, ret_id)
end

function redis_get_matching_keys(ctx, pattern, data_cb, user_data)
    ccall((:redis_get_matching_keys, libatom), Cint, (Ptr{redisContext}, Cstring, Ptr{Cvoid}, Ptr{Cvoid}), ctx, pattern, data_cb, user_data)
end

function redis_remove_key(ctx, key, unlink)
    ccall((:redis_remove_key, libatom), Bool, (Ptr{redisContext}, Cstring, Bool), ctx, key, unlink)
end

function redis_print_reply(depth, elem, reply)
    ccall((:redis_print_reply, libatom), Cvoid, (Cint, Cint, Ptr{redisReply}), depth, elem, reply)
end

function redis_print_xread_kv_items(items, n_items)
    ccall((:redis_print_xread_kv_items, libatom), Cvoid, (Ptr{redis_xread_kv_item}, Csize_t), items, n_items)
end

function redis_context_init()
    ccall((:redis_context_init, libatom), Ptr{redisContext}, ())
end

function redis_context_cleanup(ctx)
    ccall((:redis_context_cleanup, libatom), Cvoid, (Ptr{redisContext},), ctx)
end
# Julia wrapper for header: async.h
# Automatically generated using Clang.jl


function redisAsyncConnect(ip, port)
    ccall((:redisAsyncConnect, libatom), Ptr{redisAsyncContext}, (Cstring, Cint), ip, port)
end

function redisAsyncConnectBind(ip, port, source_addr)
    ccall((:redisAsyncConnectBind, libatom), Ptr{redisAsyncContext}, (Cstring, Cint, Cstring), ip, port, source_addr)
end

function redisAsyncConnectBindWithReuse(ip, port, source_addr)
    ccall((:redisAsyncConnectBindWithReuse, libatom), Ptr{redisAsyncContext}, (Cstring, Cint, Cstring), ip, port, source_addr)
end

function redisAsyncConnectUnix(path)
    ccall((:redisAsyncConnectUnix, libatom), Ptr{redisAsyncContext}, (Cstring,), path)
end

function redisAsyncSetConnectCallback(ac, fn)
    ccall((:redisAsyncSetConnectCallback, libatom), Cint, (Ptr{redisAsyncContext}, Ptr{redisConnectCallback}), ac, fn)
end

function redisAsyncSetDisconnectCallback(ac, fn)
    ccall((:redisAsyncSetDisconnectCallback, libatom), Cint, (Ptr{redisAsyncContext}, Ptr{redisDisconnectCallback}), ac, fn)
end

function redisAsyncDisconnect(ac)
    ccall((:redisAsyncDisconnect, libatom), Cvoid, (Ptr{redisAsyncContext},), ac)
end

function redisAsyncFree(ac)
    ccall((:redisAsyncFree, libatom), Cvoid, (Ptr{redisAsyncContext},), ac)
end

function redisAsyncHandleRead(ac)
    ccall((:redisAsyncHandleRead, libatom), Cvoid, (Ptr{redisAsyncContext},), ac)
end

function redisAsyncHandleWrite(ac)
    ccall((:redisAsyncHandleWrite, libatom), Cvoid, (Ptr{redisAsyncContext},), ac)
end

function redisAsyncCommandArgv(ac, fn, privdata, argc, argv, argvlen)
    ccall((:redisAsyncCommandArgv, libatom), Cint, (Ptr{redisAsyncContext}, Ptr{redisCallbackFn}, Ptr{Cvoid}, Cint, Ptr{Cstring}, Ptr{Csize_t}), ac, fn, privdata, argc, argv, argvlen)
end

function redisAsyncFormattedCommand(ac, fn, privdata, cmd, len)
    ccall((:redisAsyncFormattedCommand, libatom), Cint, (Ptr{redisAsyncContext}, Ptr{redisCallbackFn}, Ptr{Cvoid}, Cstring, Csize_t), ac, fn, privdata, cmd, len)
end
# Julia wrapper for header: dict.h
# Automatically generated using Clang.jl


function dictGenHashFunction(buf, len)
    ccall((:dictGenHashFunction, libatom), UInt32, (Ptr{Cuchar}, Cint), buf, len)
end

function dictCreate(type, privDataPtr)
    ccall((:dictCreate, libatom), Ptr{dict}, (Ptr{dictType}, Ptr{Cvoid}), type, privDataPtr)
end

function dictExpand(ht, size)
    ccall((:dictExpand, libatom), Cint, (Ptr{dict}, Culong), ht, size)
end

function dictAdd(ht, key, val)
    ccall((:dictAdd, libatom), Cint, (Ptr{dict}, Ptr{Cvoid}, Ptr{Cvoid}), ht, key, val)
end

function dictReplace(ht, key, val)
    ccall((:dictReplace, libatom), Cint, (Ptr{dict}, Ptr{Cvoid}, Ptr{Cvoid}), ht, key, val)
end

function dictDelete(ht, key)
    ccall((:dictDelete, libatom), Cint, (Ptr{dict}, Ptr{Cvoid}), ht, key)
end

function dictRelease(ht)
    ccall((:dictRelease, libatom), Cvoid, (Ptr{dict},), ht)
end

function dictFind(ht, key)
    ccall((:dictFind, libatom), Ptr{dictEntry}, (Ptr{dict}, Ptr{Cvoid}), ht, key)
end

function dictGetIterator(ht)
    ccall((:dictGetIterator, libatom), Ptr{dictIterator}, (Ptr{dict},), ht)
end

function dictNext(iter)
    ccall((:dictNext, libatom), Ptr{dictEntry}, (Ptr{dictIterator},), iter)
end

function dictReleaseIterator(iter)
    ccall((:dictReleaseIterator, libatom), Cvoid, (Ptr{dictIterator},), iter)
end
# Julia wrapper for header: fmacros.h
# Automatically generated using Clang.jl

# Julia wrapper for header: hiredis.h
# Automatically generated using Clang.jl


function redisReaderCreate()
    ccall((:redisReaderCreate, libatom), Ptr{redisReader}, ())
end

function freeReplyObject(reply)
    ccall((:freeReplyObject, libatom), Cvoid, (Ptr{Cvoid},), reply)
end

function redisFormatCommandArgv(target, argc, argv, argvlen)
    ccall((:redisFormatCommandArgv, libatom), Cint, (Ptr{Cstring}, Cint, Ptr{Cstring}, Ptr{Csize_t}), target, argc, argv, argvlen)
end

function redisFormatSdsCommandArgv(target, argc, argv, argvlen)
    ccall((:redisFormatSdsCommandArgv, libatom), Cint, (Ptr{sds}, Cint, Ptr{Cstring}, Ptr{Csize_t}), target, argc, argv, argvlen)
end

function redisFreeCommand(cmd)
    ccall((:redisFreeCommand, libatom), Cvoid, (Cstring,), cmd)
end

function redisFreeSdsCommand(cmd)
    ccall((:redisFreeSdsCommand, libatom), Cvoid, (sds,), cmd)
end

function redisConnect(ip, port)
    ccall((:redisConnect, libatom), Ptr{redisContext}, (Cstring, Cint), ip, port)
end

function redisConnectWithTimeout(ip, port, tv)
    ccall((:redisConnectWithTimeout, libatom), Ptr{redisContext}, (Cstring, Cint, timeval), ip, port, tv)
end

function redisConnectNonBlock(ip, port)
    ccall((:redisConnectNonBlock, libatom), Ptr{redisContext}, (Cstring, Cint), ip, port)
end

function redisConnectBindNonBlock(ip, port, source_addr)
    ccall((:redisConnectBindNonBlock, libatom), Ptr{redisContext}, (Cstring, Cint, Cstring), ip, port, source_addr)
end

function redisConnectBindNonBlockWithReuse(ip, port, source_addr)
    ccall((:redisConnectBindNonBlockWithReuse, libatom), Ptr{redisContext}, (Cstring, Cint, Cstring), ip, port, source_addr)
end

function redisConnectUnix(path)
    ccall((:redisConnectUnix, libatom), Ptr{redisContext}, (Cstring,), path)
end

function redisConnectUnixWithTimeout(path, tv)
    ccall((:redisConnectUnixWithTimeout, libatom), Ptr{redisContext}, (Cstring, timeval), path, tv)
end

function redisConnectUnixNonBlock(path)
    ccall((:redisConnectUnixNonBlock, libatom), Ptr{redisContext}, (Cstring,), path)
end

function redisConnectFd(fd)
    ccall((:redisConnectFd, libatom), Ptr{redisContext}, (Cint,), fd)
end

function redisReconnect(c)
    ccall((:redisReconnect, libatom), Cint, (Ptr{redisContext},), c)
end

function redisSetTimeout(c, tv)
    ccall((:redisSetTimeout, libatom), Cint, (Ptr{redisContext}, timeval), c, tv)
end

function redisEnableKeepAlive(c)
    ccall((:redisEnableKeepAlive, libatom), Cint, (Ptr{redisContext},), c)
end

function redisFree(c)
    ccall((:redisFree, libatom), Cvoid, (Ptr{redisContext},), c)
end

function redisFreeKeepFd(c)
    ccall((:redisFreeKeepFd, libatom), Cint, (Ptr{redisContext},), c)
end

function redisBufferRead(c)
    ccall((:redisBufferRead, libatom), Cint, (Ptr{redisContext},), c)
end

function redisBufferWrite(c, done)
    ccall((:redisBufferWrite, libatom), Cint, (Ptr{redisContext}, Ptr{Cint}), c, done)
end

function redisGetReply(c, reply)
    ccall((:redisGetReply, libatom), Cint, (Ptr{redisContext}, Ptr{Ptr{Cvoid}}), c, reply)
end

function redisGetReplyFromReader(c, reply)
    ccall((:redisGetReplyFromReader, libatom), Cint, (Ptr{redisContext}, Ptr{Ptr{Cvoid}}), c, reply)
end

function redisAppendFormattedCommand(c, cmd, len)
    ccall((:redisAppendFormattedCommand, libatom), Cint, (Ptr{redisContext}, Cstring, Csize_t), c, cmd, len)
end

function redisAppendCommandArgv(c, argc, argv, argvlen)
    ccall((:redisAppendCommandArgv, libatom), Cint, (Ptr{redisContext}, Cint, Ptr{Cstring}, Ptr{Csize_t}), c, argc, argv, argvlen)
end

function redisCommandArgv(c, argc, argv, argvlen)
    ccall((:redisCommandArgv, libatom), Ptr{Cvoid}, (Ptr{redisContext}, Cint, Ptr{Cstring}, Ptr{Csize_t}), c, argc, argv, argvlen)
end
# Julia wrapper for header: net.h
# Automatically generated using Clang.jl


function redisCheckSocketError(c)
    ccall((:redisCheckSocketError, libatom), Cint, (Ptr{redisContext},), c)
end

function redisContextSetTimeout(c, tv)
    ccall((:redisContextSetTimeout, libatom), Cint, (Ptr{redisContext}, timeval), c, tv)
end

function redisContextConnectTcp(c, addr, port, timeout)
    ccall((:redisContextConnectTcp, libatom), Cint, (Ptr{redisContext}, Cstring, Cint, Ptr{timeval}), c, addr, port, timeout)
end

function redisContextConnectBindTcp(c, addr, port, timeout, source_addr)
    ccall((:redisContextConnectBindTcp, libatom), Cint, (Ptr{redisContext}, Cstring, Cint, Ptr{timeval}, Cstring), c, addr, port, timeout, source_addr)
end

function redisContextConnectUnix(c, path, timeout)
    ccall((:redisContextConnectUnix, libatom), Cint, (Ptr{redisContext}, Cstring, Ptr{timeval}), c, path, timeout)
end

function redisKeepAlive(c, interval)
    ccall((:redisKeepAlive, libatom), Cint, (Ptr{redisContext}, Cint), c, interval)
end
# Julia wrapper for header: read.h
# Automatically generated using Clang.jl


function redisReaderCreateWithFunctions(fn)
    ccall((:redisReaderCreateWithFunctions, libatom), Ptr{redisReader}, (Ptr{redisReplyObjectFunctions},), fn)
end

function redisReaderFree(r)
    ccall((:redisReaderFree, libatom), Cvoid, (Ptr{redisReader},), r)
end

function redisReaderFeed(r, buf, len)
    ccall((:redisReaderFeed, libatom), Cint, (Ptr{redisReader}, Cstring, Csize_t), r, buf, len)
end

function redisReaderGetReply(r, reply)
    ccall((:redisReaderGetReply, libatom), Cint, (Ptr{redisReader}, Ptr{Ptr{Cvoid}}), r, reply)
end
# Julia wrapper for header: sds.h
# Automatically generated using Clang.jl


function sdslen(s)
    ccall((:sdslen, libatom), Csize_t, (sds,), s)
end

function sdsavail(s)
    ccall((:sdsavail, libatom), Csize_t, (sds,), s)
end

function sdssetlen(s, newlen)
    ccall((:sdssetlen, libatom), Cvoid, (sds, Csize_t), s, newlen)
end

function sdsinclen(s, inc)
    ccall((:sdsinclen, libatom), Cvoid, (sds, Csize_t), s, inc)
end

function sdsalloc(s)
    ccall((:sdsalloc, libatom), Csize_t, (sds,), s)
end

function sdssetalloc(s, newlen)
    ccall((:sdssetalloc, libatom), Cvoid, (sds, Csize_t), s, newlen)
end

function sdsnewlen(init, initlen)
    ccall((:sdsnewlen, libatom), sds, (Ptr{Cvoid}, Csize_t), init, initlen)
end

function sdsnew(init)
    ccall((:sdsnew, libatom), sds, (Cstring,), init)
end

function sdsempty()
    ccall((:sdsempty, libatom), sds, ())
end

function sdsdup(s)
    ccall((:sdsdup, libatom), sds, (sds,), s)
end

function sdsfree(s)
    ccall((:sdsfree, libatom), Cvoid, (sds,), s)
end

function sdsgrowzero(s, len)
    ccall((:sdsgrowzero, libatom), sds, (sds, Csize_t), s, len)
end

function sdscatlen(s, t, len)
    ccall((:sdscatlen, libatom), sds, (sds, Ptr{Cvoid}, Csize_t), s, t, len)
end

function sdscat(s, t)
    ccall((:sdscat, libatom), sds, (sds, Cstring), s, t)
end

function sdscatsds(s, t)
    ccall((:sdscatsds, libatom), sds, (sds, sds), s, t)
end

function sdscpylen(s, t, len)
    ccall((:sdscpylen, libatom), sds, (sds, Cstring, Csize_t), s, t, len)
end

function sdscpy(s, t)
    ccall((:sdscpy, libatom), sds, (sds, Cstring), s, t)
end

function sdstrim(s, cset)
    ccall((:sdstrim, libatom), sds, (sds, Cstring), s, cset)
end

function sdsrange(s, start, _end)
    ccall((:sdsrange, libatom), Cvoid, (sds, Cint, Cint), s, start, _end)
end

function sdsupdatelen(s)
    ccall((:sdsupdatelen, libatom), Cvoid, (sds,), s)
end

function sdsclear(s)
    ccall((:sdsclear, libatom), Cvoid, (sds,), s)
end

function sdscmp(s1, s2)
    ccall((:sdscmp, libatom), Cint, (sds, sds), s1, s2)
end

function sdssplitlen(s, len, sep, seplen, count)
    ccall((:sdssplitlen, libatom), Ptr{sds}, (Cstring, Cint, Cstring, Cint, Ptr{Cint}), s, len, sep, seplen, count)
end

function sdsfreesplitres(tokens, count)
    ccall((:sdsfreesplitres, libatom), Cvoid, (Ptr{sds}, Cint), tokens, count)
end

function sdstolower(s)
    ccall((:sdstolower, libatom), Cvoid, (sds,), s)
end

function sdstoupper(s)
    ccall((:sdstoupper, libatom), Cvoid, (sds,), s)
end

function sdsfromlonglong(value)
    ccall((:sdsfromlonglong, libatom), sds, (Clonglong,), value)
end

function sdscatrepr(s, p, len)
    ccall((:sdscatrepr, libatom), sds, (sds, Cstring, Csize_t), s, p, len)
end

function sdssplitargs(line, argc)
    ccall((:sdssplitargs, libatom), Ptr{sds}, (Cstring, Ptr{Cint}), line, argc)
end

function sdsmapchars(s, from, to, setlen)
    ccall((:sdsmapchars, libatom), sds, (sds, Cstring, Cstring, Csize_t), s, from, to, setlen)
end

function sdsjoin(argv, argc, sep)
    ccall((:sdsjoin, libatom), sds, (Ptr{Cstring}, Cint, Cstring), argv, argc, sep)
end

function sdsjoinsds(argv, argc, sep, seplen)
    ccall((:sdsjoinsds, libatom), sds, (Ptr{sds}, Cint, Cstring, Csize_t), argv, argc, sep, seplen)
end

function sdsMakeRoomFor(s, addlen)
    ccall((:sdsMakeRoomFor, libatom), sds, (sds, Csize_t), s, addlen)
end

function sdsIncrLen(s, incr)
    ccall((:sdsIncrLen, libatom), Cvoid, (sds, Cint), s, incr)
end

function sdsRemoveFreeSpace(s)
    ccall((:sdsRemoveFreeSpace, libatom), sds, (sds,), s)
end

function sdsAllocSize(s)
    ccall((:sdsAllocSize, libatom), Csize_t, (sds,), s)
end

function sdsAllocPtr(s)
    ccall((:sdsAllocPtr, libatom), Ptr{Cvoid}, (sds,), s)
end

function sds_malloc(size)
    ccall((:sds_malloc, libatom), Ptr{Cvoid}, (Csize_t,), size)
end

function sds_realloc(ptr, size)
    ccall((:sds_realloc, libatom), Ptr{Cvoid}, (Ptr{Cvoid}, Csize_t), ptr, size)
end

function sds_free(ptr)
    ccall((:sds_free, libatom), Cvoid, (Ptr{Cvoid},), ptr)
end
# Julia wrapper for header: sdsalloc.h
# Automatically generated using Clang.jl

# Julia wrapper for header: win32.h
# Automatically generated using Clang.jl

