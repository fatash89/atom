-- stream_reference: create reference from stream
--
--  Args:
--      1: Name of stream
--      2: Stream entry ID -- leave blank "" for most recent
--      3: Reference ID
--      4: Reference timeout_ms -- 0 for no timeout

-- Either get the most recent entry or get the specified
--  entry based on the third arg
local data = ""
if (ARGV[2] == "") then
    data = redis.call('xrevrange',ARGV[1],'+','-','COUNT','1')
else
    data = redis.call('xrange',ARGV[1],ARGV[2],ARGV[2])
end

-- Loop over the response. We will ket a sequence of key, value pairs
--  in order. We tell the difference between them by checking the odd/even
--  of the iterator. If the iterator is odd then it's a key, else a value.
-- For each key,value pair, make a reference at reference:id:key with the
--  value as the value.
local ref = ""
local keys = {}
for key,val in pairs(data[1][2]) do

    -- If even, do the write
    if (key % 2 == 0) then

        -- If we don't have a timeout, don't set one
        if (ARGV[4] == '0') then
            redis.call('set',ref,val)
        -- Else, set the timeout in milliseconds
        else
            redis.call('set',ref,val,'px',ARGV[4])
        end

        -- Add the key to the array
        table.insert(keys,ref)

    -- If odd, just use it for the key name
    else
        ref = ARGV[3] .. ":" .. val
    end
end

return keys
