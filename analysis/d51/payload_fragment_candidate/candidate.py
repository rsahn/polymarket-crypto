import struct,zlib
from collections import OrderedDict
from app.d5.store import Store,encode

class FragmentStore(Store):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fragments=OrderedDict()

    def depth_text(self,value):
        if type(value) is not list or len(value)>20:return encode(value)
        flat=[]
        for level in value:
            if type(level) not in (tuple,list) or len(level)!=2 or any(type(x) is not float for x in level):return encode(value)
            flat.extend(level)
        key=struct.pack('<'+'d'*len(flat),*flat)
        if key in self.fragments:
            self.fragments.move_to_end(key)
            return self.fragments[key]
        text=encode(value)
        self.fragments[key]=text
        if len(self.fragments)>1024:self.fragments.popitem(last=False)
        return text

    @staticmethod
    def merge(mapping,special):
        parts=[];chunk={}
        for key in sorted(mapping):
            if key in special:
                if chunk:parts.append(encode(chunk)[1:-1]);chunk={}
                parts.append(encode(key)+':'+special[key])
            else:chunk[key]=mapping[key]
        if chunk:parts.append(encode(chunk)[1:-1])
        return '{'+','.join(parts)+'}'

    def pack(self,value):
        if self.schema_version!=2 or type(value) is not dict or value.get('timestamp_contract')!='D5.1' or any(type(k) is not str for k in value):return super().pack(value)
        sides={}
        for side in ('up','down'):
            q=value.get(side)
            if type(q) is not dict or any(type(k) is not str for k in q):return super().pack(value)
            depths={k:self.depth_text(q[k]) for k in ('bids','asks') if k in q}
            sides[side]=self.merge(q,depths)
        text=self.merge(value,sides)
        if len(text)>=512:
            raw=text.encode('utf-8');compressed=zlib.compress(raw,1)
            if len(compressed)<len(raw):return compressed
        return text
