import { expect,it } from 'vitest';

import { readSourceStamp } from './frame-stamp';
const bytes=(hex:string)=>Uint8Array.from(hex.match(/../g)!.map(value=>Number.parseInt(value,16))).buffer;
it('reads legacy Python stamps and extended cross-box fingerprints',()=>{
 expect(readSourceStamp(bytes('00000001060528b60519ab079c4e199428f40aef3c91ec00000300010000030003000003000003000003000200000300000300002328800000000165616263'))).toEqual({streamId:'00000001-0000-0003-0000-000000000002',sourcePts:9000,frameKey:undefined});
 expect(readSourceStamp(bytes('00000001060538b60519ab079c4e199428f40aef3c91ec00000300010000030003000003000003000003000200000301000003000003000123456789abcdef0123456789abcdef800000000165616263'))).toEqual({streamId:'00000001-0000-0003-0000-000000000002',sourcePts:2**40,frameKey:'0123456789abcdef0123456789abcdef'});
});
