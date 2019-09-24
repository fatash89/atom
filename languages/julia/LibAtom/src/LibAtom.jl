module LibAtom

import Libdl

using CEnum

include(joinpath(@__DIR__, "..", "gen", "ctypes.jl"))
#const timeval = Cvoid
const timeval = Base.Libc.TimeVal
const libatom = :libatom

import Base.Libc: malloc, realloc, free

export Ctm, Ctime_t, Cclock_t

include(joinpath(@__DIR__, "..", "gen", "libatom_common.jl"))
include(joinpath(@__DIR__, "..", "gen", "libatom_api.jl"))

# export everything
#foreach(names(@__MODULE__, all=true)) do s
#    if startswith(string(s), "SOME_PREFIX")
#        @eval export $s
#    end
#end

end # module
