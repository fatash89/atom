module LibAtom

import Libdl

#TODO: uncomment below
## Load in `deps.jl`, complaining if it does not exist
#const depsjl_path = joinpath(@__DIR__, "..", "deps", "deps.jl")
#if !isfile(depsjl_path)
#    error("LibAtom was not build properly. Please run Pkg.build(\"LibAtom\").")
#end
#include(depsjl_path)
#
## Module initialization function
#function __init__()
#    check_deps()
#end

using CEnum

include("gen/ctypes.jl")
#const timeval = Cvoid
const timeval = Base.Libc.TimeVal
const libatom = :libatom

import Base.Libc: malloc, realloc, free

export Ctm, Ctime_t, Cclock_t

#include(joinpath(@__DIR__, "..", "gen", "libatom_common.jl"))
#include(joinpath(@__DIR__, "..", "gen", "libatom_api.jl"))
include("gen/libatom_common.jl")
include("gen/libatom_api.jl")

# export everything
#foreach(names(@__MODULE__, all=true)) do s
#    if startswith(string(s), "SOME_PREFIX")
#        @eval export $s
#    end
#end

end # module
